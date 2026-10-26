#define _GNU_SOURCE

#include <errno.h>
#include <fcntl.h>
#include <linux/memfd.h>
#include <poll.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/signalfd.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>
#include <wayland-client.h>

#include "wlr-layer-shell-unstable-v1-client-protocol.h"
#include "viewporter-client-protocol.h"

struct output {
    struct wl_output *proxy;
    char *name;
    struct output *next;
};

static struct wl_display *display;
static struct wl_compositor *compositor;
static struct wl_shm *shm;
static struct wp_viewporter *viewporter;
static struct wp_viewport *viewport;
static struct zwlr_layer_shell_v1 *layer_shell;
static struct output *outputs;
static struct wl_surface *surface;
static struct zwlr_layer_surface_v1 *layer_surface;
static int configured;
static int configured_width;
static int configured_height;
static int running = 1;
static int mapped;
static int signal_fd = -1;

static void output_geometry(void *data, struct wl_output *output, int32_t x,
                            int32_t y, int32_t physical_width,
                            int32_t physical_height, int32_t subpixel,
                            const char *make, const char *model,
                            int32_t transform) {
    (void)data;
    (void)output;
    (void)x;
    (void)y;
    (void)physical_width;
    (void)physical_height;
    (void)subpixel;
    (void)make;
    (void)model;
    (void)transform;
}

static void output_mode(void *data, struct wl_output *output, uint32_t flags,
                        int32_t width, int32_t height, int32_t refresh) {
    (void)data;
    (void)output;
    (void)flags;
    (void)width;
    (void)height;
    (void)refresh;
}

static void output_done(void *data, struct wl_output *output) {
    (void)data;
    (void)output;
}

static void output_scale(void *data, struct wl_output *output, int32_t factor) {
    (void)output;
    (void)data;
    (void)factor;
}

static void output_name(void *data, struct wl_output *output, const char *name) {
    (void)output;
    struct output *item = data;
    free(item->name);
    item->name = strdup(name);
}

static void output_description(void *data, struct wl_output *output,
                               const char *description) {
    (void)data;
    (void)output;
    (void)description;
}

static const struct wl_output_listener output_listener = {
    .geometry = output_geometry,
    .mode = output_mode,
    .done = output_done,
    .scale = output_scale,
    .name = output_name,
    .description = output_description,
};

static void registry_global(void *data, struct wl_registry *registry,
                            uint32_t name, const char *interface,
                            uint32_t version) {
    (void)data;
    if (strcmp(interface, wl_compositor_interface.name) == 0) {
        uint32_t bind_version = version < 4 ? version : 4;
        compositor = wl_registry_bind(registry, name, &wl_compositor_interface,
                                      bind_version);
    } else if (strcmp(interface, wl_shm_interface.name) == 0) {
        shm = wl_registry_bind(registry, name, &wl_shm_interface, 1);
    } else if (strcmp(interface, wp_viewporter_interface.name) == 0) {
        viewporter = wl_registry_bind(registry, name, &wp_viewporter_interface, 1);
    } else if (strcmp(interface, zwlr_layer_shell_v1_interface.name) == 0) {
        uint32_t bind_version = version < 4 ? version : 4;
        layer_shell = wl_registry_bind(registry, name,
                                       &zwlr_layer_shell_v1_interface,
                                       bind_version);
    } else if (strcmp(interface, wl_output_interface.name) == 0) {
        struct output *item = calloc(1, sizeof(*item));
        if (!item)
            return;
        uint32_t bind_version = version < 4 ? version : 4;
        item->proxy = wl_registry_bind(registry, name, &wl_output_interface,
                                       bind_version);
        wl_output_add_listener(item->proxy, &output_listener, item);
        item->next = outputs;
        outputs = item;
    }
}

static void registry_remove(void *data, struct wl_registry *registry,
                            uint32_t name) {
    (void)data;
    (void)registry;
    (void)name;
}

static const struct wl_registry_listener registry_listener = {
    .global = registry_global,
    .global_remove = registry_remove,
};

static void layer_configure(void *data,
                            struct zwlr_layer_surface_v1 *configured_layer,
                            uint32_t serial, uint32_t width, uint32_t height) {
    (void)data;
    zwlr_layer_surface_v1_ack_configure(configured_layer, serial);
    if (width == 0 || height == 0 || width > INT32_MAX || height > INT32_MAX) {
        fprintf(stderr, "Compositor returned an invalid layer size\n");
        running = 0;
        return;
    }
    configured_width = (int)width;
    configured_height = (int)height;
    configured = 1;
    wp_viewport_set_destination(viewport, configured_width, configured_height);
    struct wl_region *region = wl_compositor_create_region(compositor);
    wl_region_add(region, 0, 0, configured_width, configured_height);
    wl_surface_set_opaque_region(surface, region);
    wl_surface_set_input_region(surface, region);
    wl_region_destroy(region);
    if (mapped) {
        wl_surface_damage(surface, 0, 0, configured_width, configured_height);
        wl_surface_commit(surface);
    }
}

static void layer_closed(void *data,
                         struct zwlr_layer_surface_v1 *closed_layer) {
    (void)data;
    (void)closed_layer;
    running = 0;
}

static const struct zwlr_layer_surface_v1_listener layer_listener = {
    .configure = layer_configure,
    .closed = layer_closed,
};

static int make_black_buffer(struct wl_buffer **buffer_out) {
    // A uniform colour needs one pixel; viewporter scales it to the surface.
    const size_t length = sizeof(uint32_t);
    int fd = memfd_create("noctalia-screen-blackout", MFD_CLOEXEC);
    if (fd < 0 || ftruncate(fd, (off_t)length) < 0) {
        fprintf(stderr, "Could not allocate black layer buffer: %s\n",
                strerror(errno));
        if (fd >= 0)
            close(fd);
        return -1;
    }

    uint32_t *pixels = mmap(NULL, length, PROT_READ | PROT_WRITE, MAP_SHARED,
                             fd, 0);
    if (pixels == MAP_FAILED) {
        fprintf(stderr, "Could not map black layer buffer: %s\n",
                strerror(errno));
        close(fd);
        return -1;
    }
    pixels[0] = 0xff000000u;
    munmap(pixels, length);

    struct wl_shm_pool *pool = wl_shm_create_pool(shm, fd, (int32_t)length);
    *buffer_out = wl_shm_pool_create_buffer(pool, 0, 1, 1, 4,
                                            WL_SHM_FORMAT_XRGB8888);
    wl_shm_pool_destroy(pool);
    close(fd);
    return *buffer_out ? 0 : -1;
}

static struct output *find_output(const char *requested_name) {
    for (struct output *item = outputs; item; item = item->next) {
        if (item->name && strcmp(item->name, requested_name) == 0)
            return item;
    }
    return NULL;
}

static void cleanup(void) {
    if (layer_surface)
        zwlr_layer_surface_v1_destroy(layer_surface);
    if (viewport)
        wp_viewport_destroy(viewport);
    if (surface)
        wl_surface_destroy(surface);
    if (layer_shell)
        zwlr_layer_shell_v1_destroy(layer_shell);
    if (viewporter)
        wp_viewporter_destroy(viewporter);
    if (shm)
        wl_shm_destroy(shm);
    if (compositor)
        wl_compositor_destroy(compositor);
    while (outputs) {
        struct output *next = outputs->next;
        if (outputs->proxy)
            wl_output_destroy(outputs->proxy);
        free(outputs->name);
        free(outputs);
        outputs = next;
    }
    if (display) {
        wl_display_flush(display);
        wl_display_disconnect(display);
    }
    if (signal_fd >= 0)
        close(signal_fd);
}

int main(int argc, char **argv) {
    if (argc != 2) {
        fprintf(stderr, "Usage: blackout-layer MONITOR\n");
        return 2;
    }
    const char *monitor = argv[1];
    sigset_t stop_signals;
    sigemptyset(&stop_signals);
    sigaddset(&stop_signals, SIGTERM);
    sigaddset(&stop_signals, SIGINT);
    if (sigprocmask(SIG_BLOCK, &stop_signals, NULL) < 0 ||
        (signal_fd = signalfd(-1, &stop_signals, SFD_CLOEXEC | SFD_NONBLOCK)) < 0) {
        fprintf(stderr, "Could not install shutdown handler: %s\n",
                strerror(errno));
        return 1;
    }

    display = wl_display_connect(NULL);
    if (!display) {
        fprintf(stderr, "Could not connect to the Wayland compositor\n");
        return 1;
    }
    struct wl_registry *registry = wl_display_get_registry(display);
    wl_registry_add_listener(registry, &registry_listener, NULL);
    if (wl_display_roundtrip(display) < 0 ||
        wl_display_roundtrip(display) < 0) {
        fprintf(stderr, "Could not read Wayland outputs\n");
        wl_registry_destroy(registry);
        cleanup();
        return 1;
    }

    struct output *target = find_output(monitor);
    if (!compositor || !shm || !layer_shell || !viewporter || !target) {
        fprintf(stderr, "%s\n", !target
                    ? "Monitor name is not exposed by the Wayland compositor"
                    : "Compositor is missing required layer-shell or viewporter support");
        wl_registry_destroy(registry);
        cleanup();
        return 1;
    }

    surface = wl_compositor_create_surface(compositor);
    viewport = wp_viewporter_get_viewport(viewporter, surface);
    layer_surface = zwlr_layer_shell_v1_get_layer_surface(
        layer_shell, surface, target->proxy, ZWLR_LAYER_SHELL_V1_LAYER_TOP,
        "noctalia-screen-blackout");
    zwlr_layer_surface_v1_set_size(layer_surface, 0, 0);
    zwlr_layer_surface_v1_set_anchor(
        layer_surface,
        ZWLR_LAYER_SURFACE_V1_ANCHOR_TOP |
            ZWLR_LAYER_SURFACE_V1_ANCHOR_BOTTOM |
            ZWLR_LAYER_SURFACE_V1_ANCHOR_LEFT |
            ZWLR_LAYER_SURFACE_V1_ANCHOR_RIGHT);
    zwlr_layer_surface_v1_set_exclusive_zone(layer_surface, -1);
    zwlr_layer_surface_v1_set_keyboard_interactivity(
        layer_surface, ZWLR_LAYER_SURFACE_V1_KEYBOARD_INTERACTIVITY_NONE);
    zwlr_layer_surface_v1_add_listener(layer_surface, &layer_listener, NULL);
    wl_surface_commit(surface);
    wl_registry_destroy(registry);

    if (wl_display_roundtrip(display) < 0 || !configured) {
        fprintf(stderr, "Compositor did not configure the blackout layer\n");
        cleanup();
        return 1;
    }

    struct wl_buffer *buffer = NULL;
    if (make_black_buffer(&buffer) < 0) {
        cleanup();
        return 1;
    }
    wl_surface_attach(surface, buffer, 0, 0);
    wl_surface_damage(surface, 0, 0, configured_width, configured_height);
    wl_surface_commit(surface);
    mapped = 1;
    wl_display_flush(display);

    while (running) {
        while (running && wl_display_prepare_read(display) != 0) {
            if (wl_display_dispatch_pending(display) < 0) {
                running = 0;
                break;
            }
        }
        if (!running)
            break;

        int flush_blocked = 0;
        if (wl_display_flush(display) < 0) {
            if (errno == EAGAIN) {
                flush_blocked = 1;
            } else {
                wl_display_cancel_read(display);
                fprintf(stderr, "Could not flush Wayland requests\n");
                break;
            }
        }

        struct pollfd descriptors[] = {
            { .fd = wl_display_get_fd(display),
              .events = POLLIN | (flush_blocked ? POLLOUT : 0) },
            { .fd = signal_fd, .events = POLLIN },
        };
        int ready = poll(descriptors, 2, -1);
        if (ready < 0) {
            int saved_errno = errno;
            wl_display_cancel_read(display);
            if (saved_errno == EINTR)
                continue;
            fprintf(stderr, "Could not wait for Wayland events: %s\n",
                    strerror(saved_errno));
            break;
        }
        if (descriptors[1].revents & POLLIN) {
            wl_display_cancel_read(display);
            break;
        }
        if (!(descriptors[0].revents & POLLIN)) {
            wl_display_cancel_read(display);
        } else if (wl_display_read_events(display) < 0) {
            fprintf(stderr, "Lost connection to the Wayland compositor\n");
            break;
        }
        if (descriptors[0].revents & (POLLERR | POLLHUP | POLLNVAL)) {
            fprintf(stderr, "Lost connection to the Wayland compositor\n");
            break;
        }
        if (wl_display_dispatch_pending(display) < 0) {
            fprintf(stderr, "Could not dispatch Wayland events\n");
            break;
        }
    }

    wl_buffer_destroy(buffer);
    cleanup();
    return 0;
}

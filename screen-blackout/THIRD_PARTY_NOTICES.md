# Third-party notices

The original project files are offered under the MIT licence in `LICENSE`.

## wlr layer-shell protocol

`wlr-layer-shell-unstable-v1.xml` contains version 4 of the wlr layer-shell
protocol. Its original copyright and permission notice are retained in the
file and repeated below for supporting documentation. These terms continue
to apply to that file and its generated protocol definitions.

Upstream: [wlr-protocols](https://gitlab.freedesktop.org/wlroots/wlr-protocols).
The exact vendored XML has SHA-256 `996b8c66e1c2276c443336d4cb174634e8e5948823779042f244930525b79cc2`.
No upstream commit is asserted for this inherited copy.

```text
Copyright © 2017 Drew DeVault

Permission to use, copy, modify, distribute, and sell this
software and its documentation for any purpose is hereby granted
without fee, provided that the above copyright notice appear in
all copies and that both that copyright notice and this permission
notice appear in supporting documentation, and that the name of
the copyright holders not be used in advertising or publicity
pertaining to distribution of the software without specific,
written prior permission.  The copyright holders make no
representations about the suitability of this software for any
purpose.  It is provided "as is" without express or implied
warranty.

THE COPYRIGHT HOLDERS DISCLAIM ALL WARRANTIES WITH REGARD TO THIS
SOFTWARE, INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND
FITNESS, IN NO EVENT SHALL THE COPYRIGHT HOLDERS BE LIABLE FOR ANY
SPECIAL, INDIRECT OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN
AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION,
ARISING OUT OF OR IN CONNECTION WITH THE USE OR PERFORMANCE OF
THIS SOFTWARE.
```

## Build-time protocols and libraries

The build generates C definitions from the installed Wayland XDG-shell and
viewporter XML files. Their notices are included by `wayland-scanner` in the
generated source. Generated source and the resulting executable are excluded
from the Git repository and source release. The helper links against the
system Wayland client library; retain its licence notices when redistributing
that library or a binary package containing it.

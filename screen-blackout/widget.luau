local PANEL_ID = "magnus/screen-blackout:picker"
local hoverActive = noctalia.state.get("hover.active") == true

local function render_widget()
  local layout = barWidget.isVertical() and ui.column or ui.row
  barWidget.render(layout({
    width = 24,
    height = 24,
    fill = hoverActive and "primary/0.16" or "surface/0",
    radius = 8,
    align = "center",
    justify = "center",
  }, {
    ui.glyph({ name = "monitor", size = 14 }),
  }))
  barWidget.setTooltip("Hover to select monitors to black out")
end

local function set_hover_active(active)
  if hoverActive == active then return end
  hoverActive = active
  noctalia.state.set("hover.active", active)
  render_widget()
end

noctalia.state.watch("hover.active", function(value)
  local active = value == true
  if hoverActive ~= active then
    hoverActive = active
    render_widget()
  end
end)

local function schedule_close()
  noctalia.runAsync({ "sleep", "0.25" }, function()
    if noctalia.state.get("hover.button") or noctalia.state.get("hover.panel") then
      return
    end
    set_hover_active(false)
    if noctalia.state.get("hover.open") then
      noctalia.state.set("hover.open", false)
      noctalia.runAsync({ "noctalia", "msg", "panel-close", PANEL_ID })
    end
  end)
end

function update()
  render_widget()
end

function onHover(entered)
  if entered then
    noctalia.state.set("hover.button", true)
    set_hover_active(true)
    if not noctalia.state.get("hover.open") then
      noctalia.state.set("hover.open", true)
      -- Called from the bar widget so Noctalia can anchor the floating panel here.
      noctalia.togglePanel(PANEL_ID)
    end
  else
    noctalia.state.set("hover.button", false)
    schedule_close()
  end
end

function onExit(_signal, reason)
  if reason == "disable" or reason == "uninstall" or reason == "shutdown" then
    noctalia.runAsync({
      "python3", (noctalia.pluginDir() or "") .. "/blackout.py", "restore-all",
    })
  end
end

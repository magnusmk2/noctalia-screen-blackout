local outputs = {}
local statusText = ""
local busy = false
local SCRIPT = (noctalia.pluginDir() or "") .. "/blackout.py"
local render
local refresh
local close_panel
local closeGeneration = 0
local refreshGeneration = 0

local function schedule_hover_close()
  closeGeneration += 1
  local generation = closeGeneration
  noctalia.runAsync({ "sleep", "0.25" }, function()
    if generation ~= closeGeneration then return end
    if noctalia.state.get("hover.button") or noctalia.state.get("hover.panel") then return end
    if noctalia.state.get("hover.open") then
      noctalia.state.set("hover.active", false)
      noctalia.state.set("hover.open", false)
      panel.close()
    end
  end)
end

local function on_panel_hover(state)
  if state == "true" then
    closeGeneration += 1
    noctalia.state.set("hover.panel", true)
    noctalia.state.set("hover.active", true)
  else
    noctalia.state.set("hover.panel", false)
    schedule_hover_close()
  end
end

local function run(action, output, callback)
  local command = { "python3", SCRIPT, action }
  if output then
    if not string.match(output, "^[A-Za-z0-9][A-Za-z0-9._-]*$") then
      callback({ exitCode = 1, stdout = "", stderr = "Unexpected monitor name" })
      return
    end
    table.insert(command, output)
  end
  if not noctalia.runAsync(command, callback) then
    callback({ exitCode = 1, stdout = "", stderr = "Could not start the blackout helper" })
  end
end

local function toggle_output(output)
  if busy then return end
  busy = true
  render()
  run(output.active and "restore" or "blackout", output.name, function(result)
    busy = false
    if result.exitCode ~= 0 then
      noctalia.notifyError("Screen Blackout", result.stderr ~= "" and result.stderr or "Could not change " .. output.name)
    end
    refresh()
  end)
end

local function blackout_others(output)
  if busy then return end
  busy = true
  render()
  run("blackout-others", output.name, function(result)
    busy = false
    if result.exitCode ~= 0 then
      noctalia.notifyError("Screen Blackout", result.stderr ~= "" and result.stderr or "Could not black out the other displays")
    end
    refresh()
  end)
end

local function monitor_tile(output, width, height)
  return ui.column({
    width = width,
    height = height,
    fill = output.active and "#000000" or "surface_variant",
    radius = 8,
    border = output.focused and "primary" or "outline",
    borderWidth = output.focused and 2 or 1,
    align = "center",
    justify = "center",
  }, {
    ui.button({
      width = width,
      height = height,
      text = output.name .. "\n" .. (output.active and "Blacked out" or "Visible"),
      fontSize = 12,
      variant = "ghost",
      enabled = not busy,
      contentAlign = "center",
      tooltip = "Left-click to toggle. Right-click to keep this screen visible; right-click again to restore all screens.",
      onClick = function() toggle_output(output) end,
      onRightClick = function() blackout_others(output) end,
      onHover = on_panel_hover,
    }),
  })
end

local function build_monitor_map()
  if #outputs == 0 then return nil end

  local ordered = {}
  local left, top, right, bottom = nil, nil, nil, nil
  for _, output in ipairs(outputs) do
    local width = tonumber(output.width) or 0
    local height = tonumber(output.height) or 0
    local x = tonumber(output.x) or 0
    local y = tonumber(output.y) or 0
    if width > 0 and height > 0 then
      local item = { output = output, x = x, y = y, width = width, height = height }
      table.insert(ordered, item)
      left = left == nil and x or math.min(left, x)
      top = top == nil and y or math.min(top, y)
      right = right == nil and x + width or math.max(right, x + width)
      bottom = bottom == nil and y + height or math.max(bottom, y + height)
    end
  end
  if #ordered == 0 then return nil end

  table.sort(ordered, function(a, b)
    if a.x == b.x then return a.y < b.y end
    return a.x < b.x
  end)

  local spanWidth = math.max(1, right - left)
  local spanHeight = math.max(1, bottom - top)
  local scale = math.min(260 / spanWidth, 100 / spanHeight)
  local mapNodes = {}
  local previousEnd = left
  local previousStart = nil
  local hasOverlap = false

  for _, item in ipairs(ordered) do
    if previousStart ~= nil and item.x < previousEnd then hasOverlap = true end
    previousEnd = math.max(previousEnd, item.x + item.width)
    previousStart = item.x
  end

  if hasOverlap then
    -- A single column cannot show two overlapping rectangles independently;
    -- keep every output selectable in a compact fallback layout.
    local tileWidth = math.max(90, math.floor(260 / #ordered))
    for _, item in ipairs(ordered) do
      table.insert(mapNodes, monitor_tile(item.output, tileWidth, 82))
    end
    return ui.row({ gap = 8, align = "center", justify = "start" }, mapNodes), true
  end

  previousEnd = left
  for _, item in ipairs(ordered) do
    local tileWidth = math.max(1, math.floor(item.width * scale + 0.5))
    local tileHeight = math.max(1, math.floor(item.height * scale + 0.5))
    local xPosition = math.floor((item.x - left) * scale + 0.5)
    local yPosition = math.floor((item.y - top) * scale + 0.5)
    local gapWidth = math.max(0, xPosition - math.floor((previousEnd - left) * scale + 0.5))
    if gapWidth > 0 then
      table.insert(mapNodes, ui.box({ width = gapWidth, height = 1, fill = "surface/0" }))
    end

    local screen = monitor_tile(item.output, tileWidth, tileHeight)
    local offset = ui.box({ width = tileWidth, height = yPosition, fill = "surface/0" })
    table.insert(mapNodes, ui.column({ width = tileWidth, gap = 0, align = "stretch" }, { offset, screen }))
    previousEnd = item.x + item.width
  end

  return ui.row({ gap = 0, align = "start", justify = "start" }, mapNodes), false
end

render = function()
  local rows = {
    ui.row({ align = "center", justify = "space_between" }, {
      ui.label({ text = "Screen blackout", fontSize = 16, fontWeight = "bold", color = "primary", flexGrow = 1 }),
      ui.button({ glyph = "refresh", variant = "ghost", tooltip = "Refresh monitors", enabled = not busy, onClick = refresh, onHover = on_panel_hover }),
      ui.button({ glyph = "x", variant = "ghost", tooltip = "Close", onClick = close_panel, onHover = on_panel_hover }),
    }),
    ui.label({
      text = "Right-click a screen to keep it visible. Right-click it again to restore all screens.",
      fontSize = 11,
      color = "on_surface_variant",
      maxLines = 2,
    }),
  }

  local activeCount = 0
  for _, output in ipairs(outputs) do
    if output.active then activeCount += 1 end
  end
  table.insert(rows, ui.row({ align = "center", justify = "space_between" }, {
    ui.label({ text = "All monitors", fontWeight = "bold", flexGrow = 1 }),
    ui.button({
      text = activeCount > 0 and "Restore all" or "Black out all",
      variant = activeCount > 0 and "primary" or "outline",
      enabled = #outputs > 0 and not busy,
      onHover = on_panel_hover,
      onClick = function()
        if busy then return end
        busy = true
        render()
        run(activeCount > 0 and "restore-all" or "blackout-all", nil, function(result)
          busy = false
          if result.exitCode ~= 0 then
            noctalia.notifyError("Screen Blackout", result.stderr ~= "" and result.stderr or "Could not change displays")
          end
          refresh()
        end)
      end,
    }),
  }))

  local map, overlapping = build_monitor_map()
  if map then
    table.insert(rows, map)
    if overlapping then
      table.insert(rows, ui.label({
        text = "Some monitor positions overlap, so displays are shown as separate tiles.",
        fontSize = 11,
        color = "on_surface_variant",
        maxLines = 2,
      }))
    end
  elseif #outputs == 0 then
    table.insert(rows, ui.label({ text = statusText ~= "" and statusText or "No active monitors found.", color = "on_surface_variant" }))
  end

  if statusText ~= "" and #outputs > 0 then
    table.insert(rows, ui.label({ text = statusText, fontSize = 11, color = "error", maxLines = 2 }))
  end
  table.insert(rows, ui.label({
    text = "Super+Shift+F12 restores all screens.",
    fontSize = 10,
    color = "on_surface_variant",
    maxLines = 2,
  }))
  panel.render(ui.column({ gap = 6, padding = 8, onHover = on_panel_hover }, rows))
end

refresh = function()
  refreshGeneration += 1
  local generation = refreshGeneration
  statusText = ""
  render()
  run("list", nil, function(result)
    if generation ~= refreshGeneration then return end
    if result.exitCode ~= 0 then
      outputs = {}
      statusText = result.stderr ~= "" and result.stderr or "Could not query Hyprland monitors."
      render()
      return
    end
    local decoded, err = noctalia.json.decode(result.stdout)
    if type(decoded) ~= "table" then
      outputs = {}
      statusText = "Could not read monitor list: " .. tostring(err or "invalid response")
    else
      outputs = decoded
    end
    render()
  end)
end

close_panel = function()
  panel.close()
end

function onOpen()
  noctalia.state.set("hover.open", true)
  noctalia.state.set("hover.panel", false)
  refresh()
end

function onClose()
  closeGeneration += 1
  refreshGeneration += 1
  noctalia.state.set("hover.open", false)
  noctalia.state.set("hover.panel", false)
  noctalia.state.set("hover.active", noctalia.state.get("hover.button") == true)
end

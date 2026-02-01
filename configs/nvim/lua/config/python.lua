local M = {}

local function exists(path)
  return vim.loop.fs_stat(path) ~= nil
end

function M.get_python(root)
  -- Prefer ./venv, fallback to ./.venv, else system python3
  local p1 = root .. "/venv/bin/python"
  if exists(p1) then return p1 end

  local p2 = root .. "/.venv/bin/python"
  if exists(p2) then return p2 end

  return "python3"
end

return M


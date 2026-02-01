local map = vim.keymap.set
local opts = { noremap = true, silent = true }

-- File search (VS Code-ish)
map("n", "<leader>p", "<cmd>Telescope find_files<CR>", opts)
map("n", "<leader>f", "<cmd>Telescope live_grep<CR>", opts)
map("n", "<leader>b", "<cmd>Telescope buffers<CR>", opts)

-- Quick save/quit
map("n", "<leader>w", "<cmd>w<CR>", opts)
map("n", "<leader>q", "<cmd>q<CR>", opts)

-- Diagnostics quick nav
map("n", "[d", vim.diagnostic.goto_prev, opts)
map("n", "]d", vim.diagnostic.goto_next, opts)
map("n", "<leader>e", vim.diagnostic.open_float, opts)
map("n", "<leader>dl", "<cmd>Telescope diagnostics<CR>", opts)

-- Ctrl+p = fuzzy file finder (VS Code style)
vim.keymap.set("n", "<C-p>", function()
  require("telescope.builtin").find_files({ cwd = vim.fn.getcwd() })
end, { silent = true })


-- Ctrl+Shift+f equivalent (search in files)
vim.keymap.set("n", "<C-S-f>", "<cmd>Telescope live_grep<CR>", { silent = true })


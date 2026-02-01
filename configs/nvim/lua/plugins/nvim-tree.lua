return {
  "nvim-tree/nvim-tree.lua",
  dependencies = { "nvim-tree/nvim-web-devicons" },
  action = {
      open_file = {
          quit_on_open = false,
          window_picker = {
              enable = false
          }
      }
  },
  config = function()
    require("nvim-tree").setup({
      view = { width = 35 },
      renderer = {
        icons = { show = { git = true, folder = true, file = true, folder_arrow = true } },
      },
      update_focused_file = { enable = true, update_root = false },
      respect_buf_cwd = true,
      filters = {
          dotfiles = false,
          git_ignored = false
      }
    })

    vim.keymap.set("n", "<leader>e", "<cmd>NvimTreeToggle<cr>", { desc = "Explorer toggle" })
    vim.keymap.set("n", "<leader>h", "<cmd>NvimTreeFocus<cr>", { desc = "Focus file explorer", })
    vim.keymap.set("n", "<leader>l", "<C-w>l", { desc = "Focus code window", })
  end,
}


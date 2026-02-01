return {
  { "folke/which-key.nvim", opts = {} },

  { "nvim-lua/plenary.nvim" },

  {
    "nvim-telescope/telescope.nvim",
    dependencies = { "nvim-lua/plenary.nvim" },
    opts = {
      defaults = {
        file_ignore_patterns = {
          "node_modules/",
          "venv/",
          "%.venv/",
          "__pycache__/",
          "%.git/",
        },
      },
      pickers = {
          find_files = {
              hidden = true,
              no_ignore = true,
              no_ignore_parent = true
          },
      },
    },
  },

  {
    "nvim-treesitter/nvim-treesitter",
    build = ":TSUpdate",
    opts = {
      ensure_installed = { "python", "lua", "bash", "json", "yaml", "toml", "markdown" },
      highlight = { enable = true },
      indent = { enable = true },
    },
    config = function(_, opts)
      local ok, configs = pcall(require, "nvim-treesitter.configs")
      if not ok then
          return
      end
      configs.setup(opts)
    end,
  },

  {
    "lewis6991/gitsigns.nvim",
    opts = {},
  },

  -- Simple colorscheme that "just works"
  { "folke/tokyonight.nvim", priority = 1000, opts = {}, config = function()
      vim.cmd.colorscheme("tokyonight")
    end
  },
}


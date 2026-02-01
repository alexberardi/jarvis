return {
  {
    "williamboman/mason.nvim",
    cmd = { "Mason" },
    config = function()
      require("mason").setup()
    end,
  },

  {
    "williamboman/mason-lspconfig.nvim",
    dependencies = { "williamboman/mason.nvim" },
    config = function()
      require("mason-lspconfig").setup({
        -- mason package names
        ensure_installed = {
          "pyright",
          "ts_ls",
          "html",
          "cssls",
          "jsonls",
        },
        automatic_installation = true,
      })
    end,
  },

  {
    -- still keep nvim-lspconfig installed so Mason can integrate,
    -- but DO NOT use require("lspconfig") configs anymore.
    "neovim/nvim-lspconfig",
    dependencies = { "williamboman/mason-lspconfig.nvim" },
    config = function()
      -- Keymaps on attach
      vim.api.nvim_create_autocmd("LspAttach", {
        callback = function(ev)
          local opts = { buffer = ev.buf, silent = true }
          vim.keymap.set("n", "gd", vim.lsp.buf.definition, vim.tbl_extend("force", opts, { desc = "Go to definition" }))
          vim.keymap.set("n", "gD", vim.lsp.buf.declaration, vim.tbl_extend("force", opts, { desc = "Go to declaration" }))
          vim.keymap.set("n", "gr", vim.lsp.buf.references, vim.tbl_extend("force", opts, { desc = "References" }))
          vim.keymap.set("n", "K", vim.lsp.buf.hover, vim.tbl_extend("force", opts, { desc = "Hover" }))
        end,
      })

      -- Optional: diagnostics defaults
      vim.diagnostic.config({
        severity_sort = true,
        float = { border = "rounded" },
      })

      -- Neovim 0.11+ way:
      -- These names are the *lspconfig server names*.
      vim.lsp.config("pyright", {})
      vim.lsp.config("html", {})
      vim.lsp.config("cssls", {})
      vim.lsp.config("jsonls", {})

      -- TS server name varies across ecosystems; try ts_ls first, fallback to tsserver
      -- (vim.lsp.config will error if the name is unknown; protect it)
      local ok = pcall(vim.lsp.config, "ts_ls", {})
      if not ok then
        pcall(vim.lsp.config, "ts_ls", {})
      end

      -- Enable them
      vim.lsp.enable({ "pyright", "html", "cssls", "jsonls" })
      if pcall(function() vim.lsp.enable({ "ts_ls" }) end) then
        -- enabled ts_ls
      else
        pcall(function() vim.lsp.enable({ "ts_ls" }) end)
      end
    end,
  },
}


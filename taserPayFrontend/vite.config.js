import { execSync } from 'node:child_process'
import { fileURLToPath } from 'url'
import VueI18nPlugin from '@intlify/unplugin-vue-i18n/vite'
import vue from '@vitejs/plugin-vue'
import vueJsx from '@vitejs/plugin-vue-jsx'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components/vite'
import DefineOptions from 'unplugin-vue-define-options/vite'
import { defineConfig, loadEnv } from 'vite'
import Pages from 'vite-plugin-pages'
import Layouts from 'vite-plugin-vue-layouts'
import vuetify from 'vite-plugin-vuetify'
import terser from '@rollup/plugin-terser'
// import generateSitemap from 'vite-plugin-pages-sitemap'
import obfuscator from 'rollup-plugin-obfuscator'


// https://vitejs.dev/config/
function resolveBuildCommit () {
  if (process.env.BUILD_COMMIT)
    return process.env.BUILD_COMMIT
  try {
    return execSync('git rev-parse --short HEAD', { encoding: 'utf8' }).trim()
  } catch {
    return ''
  }
}

export default ({ mode }) => {
  process.env = { ...process.env, ...loadEnv (mode, process.cwd ()) }
  const buildCommit = resolveBuildCommit()

  return defineConfig ({
    plugins: [
      vue (),
      vueJsx (),
      vuetify ({
        styles: {
          configFile: 'src/styles/variables/_vuetify.scss',
        },
      }),
      Pages ({
        dirs: [ './src/pages' ],

        onRoutesGenerated: async routes => {
          // console.log({ routes })

          // generateSitemap ({
          //   routes: [ ...routes ],
          //   hostname: process.env.VITE_APP_URL,
          // })
        },
      }),
      Layouts ({
        layoutsDirs: './src/layouts/',
      }),
      Components ({
        dirs: [ 'src/@core/components', 'src/views/demos', 'src/components/ui', 'src/components/account' ],
        dts: true,
      }),
      AutoImport ({
        eslintrc: {
          enabled: true,
          filepath: './.eslintrc-auto-import.json',
        },
        imports: [ 'vue', 'vue-router', '@vueuse/core', '@vueuse/math', 'vue-i18n', 'pinia' ],
        vueTemplate: true,
      }),
      VueI18nPlugin({
        runtimeOnly: true,
        compositionOnly: true,
        include: [
          fileURLToPath(new URL('./src/plugins/i18n/locales/**', import.meta.url)),
        ],
      }),
      DefineOptions (),
      obfuscator({
        global: true,
        options: {
          debugProtection: true,
          deadCodeInjectionThreshold: 10,
          stringArray: true,
        },
      }),
    ],
    server: {
      proxy: {
        '/api': {
          target: 'https://api.pdva0.xyz/',
          changeOrigin: true,
        },
      },
    },
    define: {
      'import.meta.env.PACKAGE_VERSION': JSON.stringify(process.env.npm_package_version),
      'import.meta.env.BUILD_COMMIT': JSON.stringify(buildCommit),
      'process.env': {},
    },
    resolve: {
      alias: {
        '@': fileURLToPath (new URL ('./src', import.meta.url)),
        '@themeConfig': fileURLToPath (new URL ('./themeConfig.js', import.meta.url)),
        '@core': fileURLToPath (new URL ('./src/@core', import.meta.url)),
        '@layouts': fileURLToPath (new URL ('./src/@layouts', import.meta.url)),
        '@images': fileURLToPath (new URL ('./src/assets/images/', import.meta.url)),
        '@styles': fileURLToPath (new URL ('./src/styles/', import.meta.url)),
        '@configured-variables': fileURLToPath (new URL ('./src/styles/variables/_template.scss', import.meta.url)),
        '@axios': fileURLToPath (new URL ('./src/plugins/axios', import.meta.url)),
        '@validators': fileURLToPath (new URL ('./src/@core/utils/validators', import.meta.url)),
        'apexcharts': fileURLToPath (new URL ('node_modules/apexcharts-clevision', import.meta.url)),
      },
    },
    build: {
      chunkSizeWarningLimit: 5000,
      cssCodeSplit: false,
      rollupOptions: {
        plugins: [ terser () ],
      },
    },
    optimizeDeps: {
      exclude: [ 'vuetify' ],
      entries: [
        './src/**/*.vue',
      ],
    },
    experimental: {
      renderBuiltUrl (filename, { hostId, hostType, type }) {
        if (type === 'public') {
          return filename
        } else {
          return (process.env.VITE_ASSETS_URL || '/') + filename
        }
      },
    },
  })
}

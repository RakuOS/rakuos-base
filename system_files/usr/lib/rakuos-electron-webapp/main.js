/**
 * rakuos-webapp — Electron main process
 *
 * Usage: electron /usr/lib/rakuos-electron-webapp/ <url> <n> [custom_css]
 *
 * Uses castlabs Electron (ECS) with Widevine fully wired up.
 */

const { app, BrowserWindow, components } = require('electron');
const path = require('path');
const fs   = require('fs');

// Debug: log all argv so we can see what Electron receives
console.log('[rakuos-webapp] process.argv:', process.argv);

// Electron argv layout:
//   process.argv[0] = path to electron binary
//   process.argv[1] = path to app dir (the script dir)
//   process.argv[2] = <url>
//   process.argv[3] = <name>
//   process.argv[4] = [custom_css]
//
// BUT if extra flags like --widevine-cdm-path are passed before the app dir,
// Electron strips them from argv. So we search for the first http arg.

function parseArgs() {
    const argv = process.argv;
    let url  = null;
    let name = 'Web App';
    let css  = '';

    for (let i = 1; i < argv.length; i++) {
        const a = argv[i];
        if (a.startsWith('http://') || a.startsWith('https://')) {
            url  = a;
            name = argv[i + 1] || 'Web App';
            css  = argv[i + 2] || '';
            break;
        }
    }

    if (!url) {
        console.error('[rakuos-webapp] No URL found in argv:', argv);
        app.quit();
        return null;
    }

    return { url, name, css };
}

const parsed = parseArgs();
if (!parsed) process.exit(1);

const { url: targetUrl, name: appName, css: customCss } = parsed;
console.log('[rakuos-webapp] Launching:', targetUrl, '|', appName);

// Sanitise name → safe id
const appId = appName.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');

// Per-app isolated data dir
const dataDir = path.join(
    app.getPath('home'),
    '.local', 'share', 'rakuos', 'webapps', 'electron-data', appId
);
fs.mkdirSync(dataDir, { recursive: true });
app.setPath('userData', dataDir);
app.setName(`rakuos-webapp-${appId}`);

// Chromium flags — must be set before ready
app.commandLine.appendSwitch('autoplay-policy', 'no-user-gesture-required');
app.commandLine.appendSwitch('enable-features',
    'WidevineDrm,PlatformEncryptedMediaExtensions,HardwareSecureDecryption');
app.commandLine.appendSwitch('disable-features', 'MediaSessionService');

let win = null;

async function createWindow() {
    // Wait for Widevine CDM to initialise (castlabs ECS)
    if (components && typeof components.whenReady === 'function') {
        try {
            await components.whenReady();
            console.log('[rakuos-webapp] Widevine status:', components.status());
        } catch (e) {
            console.warn('[rakuos-webapp] components.whenReady error:', e);
        }
    }

    win = new BrowserWindow({
        width:  1280,
        height: 800,
        title:  appName,
        autoHideMenuBar: true,
        show: false,          // don't show until ready-to-show
        webPreferences: {
            plugins:          true,
            contextIsolation: false,
            nodeIntegration:  false,
            webSecurity:      true,
        },
    });

    // Show window only once page has started rendering — avoids white flash
    win.once('ready-to-show', () => win.show());

    // Spoof UA to real Chrome so streaming sites don't block CEF/Electron
    const chromeVer = process.versions.chrome || '124.0.0.0';
    win.webContents.setUserAgent(
        `Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 ` +
        `(KHTML, like Gecko) Chrome/${chromeVer} Safari/537.36`
    );

    // Inject custom CSS after every navigation if provided
    if (customCss) {
        win.webContents.on('did-finish-load', () => {
            win.webContents.insertCSS(customCss).catch(console.error);
        });
    }

    // Log load errors so we can diagnose blank windows
    win.webContents.on('did-fail-load', (event, code, desc, url) => {
        console.error(`[rakuos-webapp] Load failed: ${code} ${desc} — ${url}`);
    });

    win.webContents.on('did-finish-load', () => {
        console.log('[rakuos-webapp] Page loaded:', win.webContents.getURL());
    });

    // Keep title as app name
    win.on('page-title-updated', (e) => e.preventDefault());

    console.log('[rakuos-webapp] Loading URL:', targetUrl);
    win.loadURL(targetUrl).catch(e => {
        console.error('[rakuos-webapp] loadURL error:', e);
    });

    win.on('closed', () => { win = null; });
}

app.whenReady().then(createWindow);
app.on('window-all-closed', () => app.quit());

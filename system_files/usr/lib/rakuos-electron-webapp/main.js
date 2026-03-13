/**
 * rakuos-webapp — Electron main process
 *
 * Usage: electron /usr/lib/rakuos-electron-webapp/ <url> <name> [custom_css]
 *
 * Uses castlabs Electron (ECS) which has Widevine fully wired up.
 * components.whenReady() ensures Widevine CDM is installed before the
 * window opens — no manual CDM path needed.
 */

const { app, BrowserWindow, components, session } = require('electron');
const path = require('path');
const fs   = require('fs');

// Args: electron . <url> <name> [custom_css]
const args      = process.argv.slice(2);
const targetUrl = args[0] || 'about:blank';
const appName   = args[1] || 'Web App';
const customCss = args[2] || '';

// Sanitise name → safe id for WM_CLASS and data dir
const appId = appName.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');

// Per-app isolated user data dir — each webapp has its own cookies/storage
const dataDir = path.join(
    app.getPath('home'),
    '.local', 'share', 'rakuos', 'webapps', 'electron-data', appId
);
fs.mkdirSync(dataDir, { recursive: true });
app.setPath('userData', dataDir);

// WM_CLASS so the taskbar groups this window correctly
app.setName(`rakuos-webapp-${appId}`);

// Must be set before ready
app.commandLine.appendSwitch('autoplay-policy', 'no-user-gesture-required');
app.commandLine.appendSwitch('enable-features',
    'WidevineDrm,PlatformEncryptedMediaExtensions,HardwareSecureDecryption');

let win = null;

async function createWindow() {
    // castlabs ECS: wait for Widevine CDM to be ready before opening window
    if (components && components.whenReady) {
        await components.whenReady();
        console.log('[rakuos-webapp] Widevine CDM status:', components.status());
    }

    win = new BrowserWindow({
        width:  1280,
        height: 800,
        title:  appName,
        autoHideMenuBar: true,
        webPreferences: {
            plugins:                   true,
            contextIsolation:          false,
            nodeIntegration:           false,
            webSecurity:               true,
        },
    });

    // Spoof user agent to match Chrome so streaming sites don't block us
    const chromeVersion = process.versions.chrome || '124.0.0.0';
    win.webContents.setUserAgent(
        `Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 ` +
        `(KHTML, like Gecko) Chrome/${chromeVersion} Safari/537.36`
    );

    // Inject custom CSS on every page load if provided
    if (customCss) {
        win.webContents.on('did-finish-load', () => {
            win.webContents.insertCSS(customCss).catch(console.error);
        });
    }

    // Keep title as app name regardless of page title
    win.on('page-title-updated', (e) => e.preventDefault());

    win.loadURL(targetUrl);

    win.on('closed', () => { win = null; });
}

app.whenReady().then(createWindow);

app.on('window-all-closed', () => app.quit());

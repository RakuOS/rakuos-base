/**
 * rakuos-webapp — Electron main process
 *
 * Usage: electron /usr/lib/rakuos-electron-webapp/ <url> <name> [custom_css] [session_group] [file]
 * Uses castlabs Electron (ECS) with Widevine fully wired up.
 */

const { app, BrowserWindow, components, nativeImage, protocol } = require('electron');
const path = require('path');
const fs   = require('fs');

// Register localfile:// as a privileged scheme so fetch() can read it from
// the renderer — must happen synchronously before app.whenReady()
protocol.registerSchemesAsPrivileged([{
    scheme: 'localfile',
    privileges: { standard: true, secure: true, supportFetchAPI: true, corsEnabled: true },
}]);

console.log('[rakuos-webapp] process.argv:', process.argv);

// MIME type map for local file open
const MIME_TYPES = {
    '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    '.doc':  'application/msword',
    '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    '.xls':  'application/vnd.ms-excel',
    '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    '.ppt':  'application/vnd.ms-powerpoint',
    '.odt':  'application/vnd.oasis.opendocument.text',
    '.ods':  'application/vnd.oasis.opendocument.spreadsheet',
    '.odp':  'application/vnd.oasis.opendocument.presentation',
    '.pdf':  'application/pdf',
    '.txt':  'text/plain',
    '.csv':  'text/csv',
};

// Find the first http(s) URL in argv — immune to flag ordering
function parseArgs() {
    const argv = process.argv;
    for (let i = 1; i < argv.length; i++) {
        if (argv[i].startsWith('http://') || argv[i].startsWith('https://')) {
            const fileArg = argv[i + 4] || '';
            return {
                url:          argv[i],
                name:         argv[i + 1] || 'Web App',
                css:          argv[i + 2] || '',
                sessionGroup: argv[i + 3] || '',
                fileArg:      fileArg && fs.existsSync(fileArg) ? fileArg : '',
            };
        }
    }
    console.error('[rakuos-webapp] No URL found in argv:', argv);
    app.quit();
    return null;
}

const parsed = parseArgs();
if (!parsed) process.exit(1);

const { url: targetUrl, name: appName, css: customCss, sessionGroup, fileArg } = parsed;
console.log('[rakuos-webapp] Launching:', targetUrl, '|', appName, fileArg ? `| file: ${fileArg}` : '');

// Sanitise name → safe id
const appId = appName.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');

// Suite members share a userData dir (keyed on sessionGroup) so Electron stores
// cookies/localStorage in the same Partitions sub-directory — giving them a
// truly shared session.  Standalone apps use their own appId-keyed dir.
const groupId = sessionGroup || appId;
const dataDir = path.join(
    app.getPath('home'),
    '.local', 'share', 'rakuos', 'webapps', 'electron-data', groupId
);
fs.mkdirSync(dataDir, { recursive: true });
app.setPath('userData', dataDir);
app.setName(appName);  // use real app name so taskbar shows it correctly

// Window size persistence — per-app file inside the (possibly shared) dataDir
const stateFile = path.join(dataDir, `window-state-${appId}.json`);

function loadWindowState() {
    try {
        const s = JSON.parse(fs.readFileSync(stateFile, 'utf8'));
        // Validate saved values are reasonable
        if (s.width > 400 && s.height > 300) return s;
    } catch (_) {}
    // Default: 75% of primary display
    const { screen } = require('electron');
    const { width, height } = screen.getPrimaryDisplay().workAreaSize;
    return {
        width:  Math.round(width  * 0.75),
        height: Math.round(height * 0.75),
    };
}

function saveWindowState(win) {
    if (win.isMaximized() || win.isMinimized()) return;
    const b = win.getBounds();
    fs.writeFileSync(stateFile, JSON.stringify({
        width:  b.width,
        height: b.height,
        x:      b.x,
        y:      b.y,
    }));
}

// Chromium flags — must be before ready
app.commandLine.appendSwitch('autoplay-policy', 'no-user-gesture-required');
app.commandLine.appendSwitch('enable-features',
    'WidevineDrm,PlatformEncryptedMediaExtensions,HardwareSecureDecryption');
app.commandLine.appendSwitch('disable-features', 'MediaSessionService');

let win = null;

async function createWindow() {
    // Wait for Widevine CDM (castlabs ECS)
    if (components && typeof components.whenReady === 'function') {
        try {
            await components.whenReady();
            console.log('[rakuos-webapp] Widevine status:', components.status());
        } catch (e) {
            console.warn('[rakuos-webapp] components.whenReady error:', e);
        }
    }

    const state = loadWindowState();

    // Load app icon from the cached webapps icon dir
    const iconPath = path.join(
        app.getPath('home'),
        '.local', 'share', 'rakuos', 'webapps', 'icons', `${appId}.png`
    );
    const icon = fs.existsSync(iconPath)
        ? nativeImage.createFromPath(iconPath)
        : nativeImage.createEmpty();

    win = new BrowserWindow({
        width:           state.width,
        height:          state.height,
        x:               state.x,
        y:               state.y,
        title:           appName,
        icon:            icon,          // taskbar + title bar icon
        autoHideMenuBar: true,
        show:            false,         // show only on ready-to-show
        webPreferences: {
            plugins:          true,
            contextIsolation: false,
            nodeIntegration:  false,
            webSecurity:      true,
            // Share session (cookies, storage) across suite members; standalone apps get their own
            partition:        `persist:${sessionGroup || appId}`,
        },
    });

    // If a local file was passed, register localfile:// protocol on this window's
    // session so the renderer can fetch the file data via fetch('localfile://file')
    if (fileArg) {
        const fileExt  = path.extname(fileArg).toLowerCase();
        const fileName = path.basename(fileArg);
        const mimeType = MIME_TYPES[fileExt] || 'application/octet-stream';

        win.webContents.session.protocol.registerBufferProtocol('localfile', (request, respond) => {
            try {
                const data = fs.readFileSync(fileArg);
                respond({
                    mimeType,
                    data,
                    headers: { 'Access-Control-Allow-Origin': '*' },
                });
            } catch (e) {
                console.error('[rakuos-webapp] localfile read error:', e);
                respond({ error: -2 });
            }
        });

        // Override window.showOpenFilePicker on dom-ready so it returns our file
        // instead of showing the OS file dialog
        const injectFileOverride = () => {
            const safeFileName = fileName.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
            const safeMime     = mimeType.replace(/"/g, '\\"');
            win.webContents.executeJavaScript(`
                (function() {
                    if (window.__rakuos_file_injected) return;
                    window.__rakuos_file_injected = true;
                    window.showOpenFilePicker = async function() {
                        const resp = await fetch('localfile://file');
                        const buf  = await resp.arrayBuffer();
                        const file = new File([buf], "${safeFileName}", { type: "${safeMime}" });
                        return [{
                            kind: 'file',
                            name: "${safeFileName}",
                            getFile:           async () => file,
                            isSameEntry:       async () => false,
                            queryPermission:   async () => 'granted',
                            requestPermission: async () => 'granted',
                        }];
                    };
                    console.log('[rakuos-webapp] showOpenFilePicker overridden for: ${safeFileName}');
                })();
            `).catch(console.error);
        };

        win.webContents.on('dom-ready', injectFileOverride);
        win.webContents.on('did-navigate', injectFileOverride);

        // Auto-click the upload button once the page finishes loading
        win.webContents.on('did-finish-load', () => {
            setTimeout(() => {
                win.webContents.executeJavaScript(`
                    (function() {
                        // Try known upload button selectors (most specific first)
                        const selectors = [
                            "button[data-testid='0301']",   // Microsoft Word/Excel/PPT
                            "button[aria-label*='pload']",
                            "input[type='file']",
                        ];
                        for (const sel of selectors) {
                            const el = document.querySelector(sel);
                            if (el) {
                                console.log('[rakuos-webapp] auto-clicking upload:', sel);
                                el.click();
                                return;
                            }
                        }
                        // Generic text search
                        for (const btn of document.querySelectorAll('button, [role="button"]')) {
                            const t = (btn.innerText || btn.textContent || '').toLowerCase();
                            if (t.includes('upload') || t.includes('open file')) {
                                console.log('[rakuos-webapp] auto-clicking upload by text:', t.trim());
                                btn.click();
                                return;
                            }
                        }
                        console.log('[rakuos-webapp] no upload button found — user must click manually');
                    })();
                `).catch(console.error);
            }, 1500);
        });
    }

    // Wayland: set app_id so compositor uses the right icon
    if (process.platform === 'linux') {
        win.setTitle(appName);
        // app.setName() above handles WM_CLASS for X11
        // For Wayland, pass --ozone-platform-hint=auto and set the icon
        app.commandLine.appendSwitch('ozone-platform-hint', 'auto');
    }

    // Show window once page starts rendering
    win.once('ready-to-show', () => win.show());

    // Save window size/position on resize and move
    win.on('resize', () => saveWindowState(win));
    win.on('move',   () => saveWindowState(win));
    win.on('close',  () => saveWindowState(win));

    // Spoof UA to real Chrome
    const chromeVer = process.versions.chrome || '124.0.0.0';
    win.webContents.setUserAgent(
        `Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 ` +
        `(KHTML, like Gecko) Chrome/${chromeVer} Safari/537.36`
    );

    // Inject custom CSS as early as possible (dom-ready fires when HTML is
    // parsed, before external resources — eliminates the flash of unstyled content)
    if (customCss) {
        const injectCss = () => win.webContents.insertCSS(customCss).catch(console.error);
        win.webContents.on('dom-ready', injectCss);
        // Re-inject on full navigations (multi-page sites)
        win.webContents.on('did-navigate', injectCss);
    }

    win.webContents.on('did-fail-load', (event, code, desc, url) => {
        console.error(`[rakuos-webapp] Load failed: ${code} ${desc} — ${url}`);
    });

    win.webContents.on('did-finish-load', () => {
        console.log('[rakuos-webapp] Page loaded:', win.webContents.getURL());
    });

    // Keep title bar as app name
    win.on('page-title-updated', (e) => e.preventDefault());

    console.log('[rakuos-webapp] Loading URL:', targetUrl);
    win.loadURL(targetUrl).catch(e => {
        console.error('[rakuos-webapp] loadURL error:', e);
    });

    win.on('closed', () => { win = null; });
}

app.whenReady().then(createWindow);
app.on('window-all-closed', () => app.quit());

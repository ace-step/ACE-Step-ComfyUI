import { app } from "../../scripts/app.js";

const SERVER_NODES = [
    "AceStepText2MusicServer",
];

function hideWidget(node, widget) {
    if (widget._hidden) return;
    widget._hidden = true;
    widget._origType = widget.type;
    widget._origComputeSize = widget.computeSize;
    widget.type = "hidden";
    widget.computeSize = () => [0, -4];
    const idx = node.widgets.indexOf(widget);
    if (idx >= 0) {
        widget._origIndex = idx;
        node.widgets.splice(idx, 1);
    }
}

function showWidget(node, widget) {
    if (!widget._hidden) return;
    widget._hidden = false;
    widget.type = widget._origType;
    widget.computeSize = widget._origComputeSize;
    delete widget._origType;
    delete widget._origComputeSize;
    if (!node.widgets.includes(widget)) {
        const idx = Math.min(widget._origIndex ?? node.widgets.length, node.widgets.length);
        node.widgets.splice(idx, 0, widget);
    }
    delete widget._origIndex;
}

function recalcSize(node, extraH = 0) {
    const sz = node.computeSize();
    node.setSize([Math.max(sz[0], node.size[0]), sz[1] + extraH]);
}

function setupApiKeyMasking(node) {
    const w = node.widgets.find(w => w.name === "api_key");
    if (!w) return;
    let realKey = "";
    w.serializeValue = async () => realKey;
    w.callback = function (value) {
        if (!value) { realKey = ""; return; }
        if (/^●+$/.test(value)) return;
        realKey = value;
        w.value = "●".repeat(Math.min(value.length, 16));
    };
}

function setupServerNode(node) {
    setupApiKeyMasking(node);

    const modeW = node.widgets.find(w => w.name === "mode");
    const urlW = node.widgets.find(w => w.name === "server_url");
    const keyW = node.widgets.find(w => w.name === "api_key");
    if (!modeW || !urlW) return;

    const btnW = node.addWidget("button", "🔑 Get API Key", null, () => {
        window.open("https://acemusic.ai/api-key", "_blank");
    });
    btnW.serialize = false;

    const CLOUD = "https://api.acemusic.ai";
    const LOCAL = "http://127.0.0.1:8002";

    function update() {
        const isLocal = modeW.value === "local";
        if (urlW.value === CLOUD || urlW.value === LOCAL || !urlW.value.trim()) {
            urlW.value = isLocal ? LOCAL : CLOUD;
        }
        if (keyW) { isLocal ? hideWidget(node, keyW) : showWidget(node, keyW); }
        isLocal ? hideWidget(node, btnW) : showWidget(node, btnW);
        recalcSize(node);
    }

    const orig = modeW.callback;
    modeW.callback = function (...args) {
        if (orig) orig.apply(this, args);
        update();
    };
    update();
}

function setupGenParamsToggles(node) {
    // Master list: canonical widget order, captured once.
    const masterWidgets = node.widgets.slice();
    const origTypes = new Map();
    const origCompute = new Map();
    for (const w of masterWidgets) {
        origTypes.set(w, w.type);
        origCompute.set(w, w.computeSize);
    }

    const byName = (n) => masterWidgets.find(w => w.name === n);
    const sampleModeW = byName("sample_mode");
    const autoW = byName("auto");
    const repaintW = byName("is_repaint");

    const TEXT_ROWS = { caption: 3, lyrics: 7, sample_query: 4 };
    let extraHeight = 0;
    for (const w of masterWidgets) {
        if (TEXT_ROWS[w.name] && w.inputEl) {
            const defaultRows = w.inputEl.rows || 3;
            w.inputEl.rows = TEXT_ROWS[w.name];
            w.inputEl.style.minHeight = (TEXT_ROWS[w.name] * 1.4) + "em";
            extraHeight += (TEXT_ROWS[w.name] - defaultRows) * 18;
        }
    }

    function computeVisible() {
        const vis = new Set();
        const isSample = sampleModeW && sampleModeW.value;

        vis.add("sample_mode");

        if (isSample) {
            vis.add("sample_query");
            vis.add("is_instrumental");
            vis.add("vocal_language");
        } else {
            vis.add("caption");
            vis.add("lyrics");
            vis.add("vocal_language");
            vis.add("auto");
            vis.add("is_repaint");

            const isAuto = autoW && autoW.value;
            if (!isAuto) {
                vis.add("bpm");
                vis.add("key");
                vis.add("duration");
                vis.add("time_signature");
            }

            const isRepaint = repaintW && repaintW.value;
            if (isRepaint) {
                vis.add("repaint_start");
                vis.add("repaint_end");
            } else {
                vis.add("cover_strength");
                vis.add("remix_strength");
            }
        }
        return vis;
    }

    function update() {
        const vis = computeVisible();

        // Rebuild node.widgets in master order, only including visible ones.
        node.widgets.length = 0;
        for (const w of masterWidgets) {
            if (vis.has(w.name)) {
                w.type = origTypes.get(w);
                w.computeSize = origCompute.get(w);
                w._hidden = false;
                node.widgets.push(w);
            } else {
                w.type = "hidden";
                w.computeSize = () => [0, -4];
                w._hidden = true;
            }
        }

        recalcSize(node, extraHeight);
    }

    for (const toggleW of [sampleModeW, autoW, repaintW]) {
        if (!toggleW) continue;
        const orig = toggleW.callback;
        toggleW.callback = function (...args) {
            if (orig) orig.apply(this, args);
            update();
        };
    }
    update();
}

function setupShowText(node) {
    const el = document.createElement("textarea");
    el.readOnly = true;
    el.style.cssText =
        "width:100%;background:transparent;color:inherit;border:none;" +
        "resize:none;font:inherit;padding:4px;opacity:0.85;outline:none;" +
        "white-space:pre-wrap;word-wrap:break-word;overflow-y:auto;";
    el.rows = 4;

    const textWidget = node.addDOMWidget("ace_text_output", "customtext", el, {
        serialize: false,
        getValue() { return el.value; },
        setValue(v) { el.value = v || ""; },
    });

    node.onExecuted = function (data) {
        if (data?.text?.[0] != null) {
            el.value = data.text[0];
            const lines = (data.text[0].match(/\n/g) || []).length + 1;
            const rows = Math.max(4, Math.min(lines, 20));
            el.rows = rows;
            const h = Math.max(120, Math.min(rows * 18 + 80, 500));
            node.setSize([Math.max(node.size[0], 300), h]);
        }
    };
}

function setupAudioCodes(node) {
    node.onExecuted = function (data) {
        const codes = data?.audio_codes?.[0];
        if (codes == null) return;
        const w = node.widgets.find(w => w.name === "audio_codes");
        if (w) {
            w.value = codes;
            recalcSize(node);
        }
    };
}

app.registerExtension({
    name: "AceStep.NodeExtensions",
    nodeCreated(node) {
        if (SERVER_NODES.includes(node.comfyClass)) {
            requestAnimationFrame(() => setupServerNode(node));
        }
        if (node.comfyClass === "AceStepText2MusicGenParams") {
            requestAnimationFrame(() => setupGenParamsToggles(node));
        }
        if (node.comfyClass === "AceStepShowText") {
            requestAnimationFrame(() => setupShowText(node));
        }
        if (node.comfyClass === "AceStepAudioCodes") {
            requestAnimationFrame(() => setupAudioCodes(node));
        }
    },
});

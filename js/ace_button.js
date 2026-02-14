import { app } from "../../scripts/app.js";

function hideWidget(node, widget) {
    if (widget._hidden) return;
    widget._hidden = true;
    widget._origType = widget.type;
    widget._origComputeSize = widget.computeSize;
    widget.type = "hidden";
    widget.computeSize = () => [0, -4];
}

function showWidget(node, widget) {
    if (!widget._hidden) return;
    widget._hidden = false;
    widget.type = widget._origType;
    widget.computeSize = widget._origComputeSize;
    delete widget._origType;
    delete widget._origComputeSize;
}

app.registerExtension({
    name: "AceStep.NodeExtensions",

    nodeCreated(node) {
        if (node.comfyClass !== "AceStepMusicGen") return;

        const REPAINT_WIDGETS = ["repainting_start", "repainting_end"];
        const COVER_WIDGETS = ["audio_cover_strength"];

        function updateVisibility() {
            const taskWidget = node.widgets.find(w => w.name === "task_type");
            if (!taskWidget) return;

            const task = taskWidget.value;

            for (const w of node.widgets) {
                if (REPAINT_WIDGETS.includes(w.name)) {
                    task === "repaint" ? showWidget(node, w) : hideWidget(node, w);
                } else if (COVER_WIDGETS.includes(w.name)) {
                    task === "cover" ? showWidget(node, w) : hideWidget(node, w);
                }
            }

            const sz = node.computeSize();
            node.setSize([Math.max(sz[0], node.size[0]), sz[1]]);
        }

        requestAnimationFrame(() => {
            const taskWidget = node.widgets.find(w => w.name === "task_type");
            if (taskWidget) {
                const origCallback = taskWidget.callback;
                taskWidget.callback = function (...args) {
                    if (origCallback) origCallback.apply(this, args);
                    updateVisibility();
                };
            }
            updateVisibility();
        });

        // --- API Key masking ---
        const apiKeyWidget = node.widgets.find(w => w.name === "api_key");
        if (apiKeyWidget) {
            let realKey = "";

            // Return real key for execution, not the masked display value
            apiKeyWidget.serializeValue = async () => realKey;

            apiKeyWidget.callback = function (value) {
                if (!value) {
                    realKey = "";
                    return;
                }
                // Ignore if user submitted the mask unchanged
                if (/^●+$/.test(value)) return;
                realKey = value;
                apiKeyWidget.value = "●".repeat(Math.min(value.length, 16));
            };
        }

        // --- Get API Key button ---
        const btn = node.addWidget("button", "🔑 Get API Key", null, () => {
            window.open("https://acemusic.ai/api-key", "_blank");
        });
        btn.serialize = false;
    },
});

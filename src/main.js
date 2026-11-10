window.localPixels = {}
window.localPresets = {};

const activePreviews = new Map();

const presetName = (name) => {
    const builtIns = {
        "🩷": "Love", "🎉": "Party", "🙂": "Happy",
        "🫂": "Hug", "🌈": "Rainbow", "🍰": "Cake",
    };
    return builtIns[name] || name;
};

const createPresetLabel = (name, emoji) => {
    const label = document.createElement("span");
    const glyph = name.match(/\p{Extended_Pictographic}(?:\uFE0F|\p{Emoji_Modifier})?(?:\u200D\p{Extended_Pictographic}(?:\uFE0F|\p{Emoji_Modifier})?)*/u);
    label.textContent = emoji || (glyph ? glyph[0] : "🔖");
    label.setAttribute("class", "preset-label");
    label.setAttribute("title", presetName(name));
    label.setAttribute("aria-label", presetName(name));
    label.setAttribute("tabindex", "0");
    label.setAttribute("data-bs-toggle", "tooltip");
    label.setAttribute("data-bs-placement", "top");
    return label;
};

const setPreviewButton = (button, playing) => {
    const label = playing ? "Stop preview" : "Preview";
    button.setAttribute("aria-label", label);
    button.setAttribute("title", label);
    button.querySelector("i").setAttribute("class",
        playing ? "bi bi-stop-fill" : "bi bi-play-fill");
    const tooltip = bootstrap.Tooltip.getInstance?.(button);
    tooltip?.setContent({ ".tooltip-inner": label });
};

const renderPixel = (element, pixel) => {
    // Strong colour plus a variable halo suggests emitted light on a screen.
    const brightness = clamp(pixel[3]);
    const off = brightness === 0 || pixel.slice(0, 3).every(channel => channel === 0);
    const intensity = Math.sqrt(brightness);
    const colour = pixel.slice(0, 3).join(", ");
    // Keep white neutral on dark pages and distinct from off on light pages.
    const white = !off && pixel.slice(0, 3).every(channel => channel === 255);
    const outline = `inset 0 0 0 1px rgba(0, 0, 0, ${white ? 0.4 : 0.12})`;
    element.style.backgroundColor = off ? "transparent"
        : `rgba(${colour}, ${white ? 1 : 0.65 + 0.35 * intensity})`;
    element.style.boxShadow = off || brightness <= 0.1 ? outline
        : `${outline}, 0 0 ${2 + 8 * intensity}px ${2 * intensity}px rgba(${colour}, ${0.2 + 0.5 * intensity})`;
};

const paintPreview = (row, pixels) => {
    row.querySelectorAll(".pixel").forEach((element, i) => {
        renderPixel(element, pixels[i]);
    });
};

const stopPreview = (device) => {
    const preview = activePreviews.get(device);
    if (!preview)
        return;
    clearTimeout(preview.timer);
    activePreviews.delete(device);
    setPreviewButton(preview.button, false);
    preview.button.setAttribute("aria-pressed", "false");
    preview.status.textContent = "Preview stopped. Browser only.";
    paintPreview(preview.row, preview.idleFrame);
};

const togglePreview = (device, effect, row, button, status) => {
    const current = activePreviews.get(device);
    const wasPlaying = current && current.row === row;
    stopPreview(device);
    if (wasPlaying)
        return;
    const frame = effect.create(Date.now() / 1000);
    const start = performance.now();
    const preview = { row, button, status, idleFrame: frame(effect.duration) };
    activePreviews.set(device, preview);
    setPreviewButton(button, true);
    button.setAttribute("aria-pressed", "true");
    status.textContent = `Previewing ${effect.duration}s. Browser only.`;
    const tick = () => {
        const elapsed = (performance.now() - start) / 1000;
        if (elapsed >= effect.duration) {
            stopPreview(device);
            paintPreview(row, effect.staysLit ? frame(effect.duration) : Array.from(
                { length: 8 }, () => [0, 0, 0, 0]));
            status.textContent = "Preview finished. Browser only.";
            return;
        }
        paintPreview(row, frame(elapsed));
        preview.timer = setTimeout(tick, 50);
    };
    tick();
};

const addSpecialPresets = (device, container) => {
    SPECIAL_PRESETS.forEach(effect => {
        const row = document.createElement("div");
        row.setAttribute("class", "simulator special-preset");
        const ol = document.createElement("ol");
        ol.appendChild(createPresetLabel(effect.name, effect.emoji));
        for (let i = 0; i < 8; i++) {
            const pixel = document.createElement("li");
            pixel.setAttribute("class", "pixel");
            ol.appendChild(pixel);
            ol.appendChild(document.createTextNode(" "));
        }
        row.appendChild(ol);
        const controls = document.createElement("div");
        controls.setAttribute("class", "btn-group");
        controls.setAttribute("role", "group");
        controls.setAttribute("aria-label", effect.name + " controls");
        const status = document.createElement("small");
        status.setAttribute("class", "visually-hidden");
        status.setAttribute("aria-live", "polite");
        status.textContent = `${effect.duration}s animation. Browser-only preview.`;
        const button = (label, icon, action) => {
            const element = document.createElement("button");
            element.setAttribute("class", "btn btn-sm btn-outline-secondary");
            element.setAttribute("aria-label", label);
            element.setAttribute("title", label);
            element.setAttribute("data-bs-toggle", "tooltip");
            element.setAttribute("data-bs-placement", "bottom");
            const glyph = document.createElement("i");
            glyph.setAttribute("class", "bi bi-" + icon);
            glyph.setAttribute("aria-hidden", "true");
            element.appendChild(glyph);
            element.addEventListener("click", action);
            controls.appendChild(element);
            return element;
        };
        const previewButton = button("Preview", "play-fill",
            () => togglePreview(device, effect, row, previewButton, status));
        previewButton.setAttribute("aria-pressed", "false");
        button("Apply to device", "lightbulb", () => pressButton(device, effect.id));
        const sendButton = button("Send to partner", "send", () => {
            stopPreview(device);
            const partner = getPartnerDevice(device);
            if (partner)
                pressButton(partner, effect.id);
        });
        sendButton.disabled = !getPartnerDevice(device);
        ol.appendChild(controls);
        row.appendChild(status);
        container.appendChild(row);
        paintPreview(row, effect.create(0)(effect.duration));
    });
};

const componentToHex = (c) => {
    hex = c.toString(16);
    return hex.length == 1 ? "0" + hex : hex;
}

const rgbToHex = (r, g, b) => {
    return "#" + componentToHex(r) + componentToHex(g) + componentToHex(b);
}

const hexToRgb = (hex) => {
    var result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
    return result ? [
        parseInt(result[1], 16),
        parseInt(result[2], 16),
        parseInt(result[3], 16)
    ] : null;
}

const getTargetDevice = (element) => {
    return element.closest(".device").id;
}

const setLocalPixels = (device, pixels) => {
    window.localPixels[device] = pixels;
    const sim = document.getElementById(device);
    const simPixels = sim.querySelectorAll('.simulator.card-body .pixel');
    pixels.forEach((pixel, i) => renderPixel(simPixels[i], pixel));
}

const setLocalPresets = (device, presets) => {
    stopPreview(device);
    window.localPresets[device] = presets;
    container = document.querySelector("#" + device + " .presets");
    container.innerText = "";
    presets.forEach((preset) => {
        let name = preset["name"];
        let div = document.createElement('div');
        div.setAttribute("class", "simulator");
        div.setAttribute("name", name);
        let ol = document.createElement("ol");
        ol.appendChild(createPresetLabel(name));
        preset["pixels"].forEach((pixel) => {
            let li = document.createElement('li');
            li.setAttribute("class", "pixel");
            renderPixel(li, pixel);
            ol.appendChild(li);
            ol.appendChild(document.createTextNode(" "));
        })

        buttonGroup = document.createElement('div');
        buttonGroup.setAttribute("class", "btn-group");
        buttonGroup.setAttribute("role", "group");

        // load preset button
        loadButton = document.createElement('button');
        loadButton.setAttribute("class", "btn btn-sm btn-outline-secondary");
        loadButton.setAttribute("onclick", "loadPreset(getTargetDevice(this), '" + name + "');");
        loadButton.setAttribute("data-bs-toggle", "tooltip");
        loadButton.setAttribute("data-bs-placement", "bottom");
        loadButton.setAttribute("title", "Load preset");
        loadButton.setAttribute("aria-label", "Load preset");
        loadIcon = document.createElement("i");
        loadIcon.setAttribute("class", "bi bi-pencil-square");
        loadButton.appendChild(loadIcon);
        buttonGroup.appendChild(loadButton);

        const applyButton = document.createElement("button");
        applyButton.setAttribute("class", "btn btn-sm btn-outline-secondary");
        applyButton.setAttribute("aria-label", "Apply to device");
        applyButton.setAttribute("title", "Apply to device");
        applyButton.setAttribute("data-bs-toggle", "tooltip");
        applyButton.setAttribute("data-bs-placement", "bottom");
        applyButton.addEventListener("click", () => {
            stopPreview(device);
            publishMessage(device, { command: "setPixels", pixels: preset["pixels"] });
        });
        const applyIcon = document.createElement("i");
        applyIcon.setAttribute("class", "bi bi-lightbulb");
        applyIcon.setAttribute("aria-hidden", "true");
        applyButton.appendChild(applyIcon);
        buttonGroup.appendChild(applyButton);

        // send preset button
        sendButton = document.createElement('button');
        sendButton.setAttribute("class", "btn btn-sm btn-outline-secondary");
        sendButton.setAttribute("onclick", "loadPreset(getTargetDevice(this), '" + name + "'); setRemotePixels(getTargetDevice(this));");
        sendButton.setAttribute("data-bs-toggle", "tooltip");
        sendButton.setAttribute("data-bs-placement", "bottom");
        sendButton.setAttribute("title", "Send preset");
        sendButton.setAttribute("aria-label", "Send preset");
        sendIcon = document.createElement("i");
        sendIcon.setAttribute("class", "bi bi-send");
        sendButton.appendChild(sendIcon);
        buttonGroup.appendChild(sendButton);

        if (!preset["default"]) {
            // rename preset button
            renameButton = document.createElement('button');
            renameButton.setAttribute("class", "btn btn-sm btn-outline-secondary");
            renameButton.setAttribute("onclick", "renamePreset(getTargetDevice(this), '" + name + "');");
            renameButton.setAttribute("data-bs-toggle", "tooltip");
            renameButton.setAttribute("data-bs-placement", "bottom");
            renameButton.setAttribute("title", "Rename preset");
            renameButton.setAttribute("aria-label", "Rename preset");
            renameIcon = document.createElement("i");
            renameIcon.setAttribute("class", "bi bi-pencil");
            renameButton.appendChild(renameIcon);
            buttonGroup.appendChild(renameButton);

            // delete preset button
            deleteButton = document.createElement('button');
            deleteButton.setAttribute("class", "btn btn-sm btn-outline-secondary");
            deleteButton.setAttribute("onclick", "deletePreset(getTargetDevice(this), '" + name + "');");
            deleteButton.setAttribute("data-bs-toggle", "tooltip");
            deleteButton.setAttribute("data-bs-placement", "bottom");
            deleteButton.setAttribute("title", "Delete preset");
            deleteButton.setAttribute("aria-label", "Delete preset");
            deleteIcon = document.createElement("i");
            deleteIcon.setAttribute("class", "bi bi-trash");
            deleteButton.appendChild(deleteIcon);
            buttonGroup.appendChild(deleteButton);
        }

        ol.appendChild(buttonGroup);
        div.appendChild(ol);
        container.appendChild(div);
    })
    addSpecialPresets(device, container);
    const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]')
    const tooltipList = [...tooltipTriggerList].map(tooltipTriggerEl => new bootstrap.Tooltip(tooltipTriggerEl))
}

const fill = (device) => {
    pixels = document.querySelectorAll('#' + device + ' .custom .pixel');
    color = pixels[0].querySelector("input[name=color]").value;
    brightness = pixels[0].querySelector("input[name=brightness]").value;
    for (i = 1; i < pixels.length; i++) {
        pixels[i].querySelector("input[name=color]").value = color;
        pixels[i].querySelector("input[name=brightness]").value = brightness;
    }
}

const getLocalPixels = (device) => {
    let pixels = []
    document.querySelectorAll('#' + device + ' .custom .pixel').forEach((pixel) => {
        color = hexToRgb(pixel.querySelector("input[name=color]").value);
        brightness = pixel.querySelector("input[name=brightness]").value / 10;
        pixels.push([...color, brightness])
    });
    return pixels;
}

const getRemoteState = (device) => {
    if (device === undefined)
        device = getTargetDevice();
    getRemotePixels(device);
    getRemotePresets(device);
}

const getRemotePixels = (device) => {
    publishMessage(device, { command: "getPixels" });
}

const getRemotePresets = (device) => {
    publishMessage(device, { command: "getPresets" });
}

const pressButton = (device, button) => {
    stopPreview(device);
    publishMessage(device, { command: "pressButton", button });
};

// The 2026 Diwali window from 6 to 11 November, in the browser's local time.
// Only the shortcut is seasonal; the celebration can be triggered year-round.
const DIWALI_SEASON = {
    start: new Date(2026, 10, 6),
    end: new Date(2026, 10, 12),
};

const isDiwaliSeason = (date = new Date()) => {
    return date >= DIWALI_SEASON.start && date < DIWALI_SEASON.end;
};

const updateDiwaliSeason = (date = new Date()) => {
    let inSeason = isDiwaliSeason(date);
    document.querySelectorAll(".diwali-season").forEach((element) => {
        element.classList.toggle("d-none", !inSeason);
    });
};

const getPartnerDevice = (device) => {
    let partner = config.devices.find(({ id }) => id !== device);
    return partner ? partner.id : undefined;
};

const lightDiyas = (device) => {
    pressButton(device, "diwali");
};

const sendDiyasToPartner = (device) => {
    let partner = getPartnerDevice(device);
    if (partner)
        lightDiyas(partner);
};

const clearRemotePixels = (device) => {
    stopPreview(device);
    publishMessage(device, { command: "clearPixels" });
};

const setRemotePixels = (device) => {
    stopPreview(device);
    message = { command: "setPixels", pixels: getLocalPixels(device) };
    publishMessage(device, message);
};

const loadLocalPixels = (device) => {
    stopPreview(device);
    let pixels = document.querySelectorAll('#' + device + ' .custom .pixel');
    for (i = 0; i < window.localPixels[device].length; i++) {
        let color = window.localPixels[device][i].slice(0, 3);
        let brightness = window.localPixels[device][i][3];
        pixels[i].querySelector("input[name=color]").value = rgbToHex(...color);
        pixels[i].querySelector("input[name=brightness]").value = brightness * 10;
    }
}

const loadPreset = (device, presetName) => {
    stopPreview(device);
    let preset = window.localPresets[device].find(({ name }) => name === presetName);
    pixels = document.getElementById(device).querySelectorAll('.custom .pixel');
    for (i = 0; i < preset["pixels"].length; i++) {
        let color = preset["pixels"][i].slice(0, 3);
        let brightness = preset["pixels"][i][3];
        pixels[i].querySelector("input[name=color]").value = rgbToHex(...color);
        pixels[i].querySelector("input[name=brightness]").value = brightness * 10;
    }
};

const savePreset = (device) => {
    let name = prompt("Provide a name for the preset:");
    if (name === null || name === "")
        return;
    else {
        let pixels = getLocalPixels(device);
        publishMessage(device, { command: "savePreset", name, pixels });
    }
}

const renamePreset = (device, fromName) => {
    let toName = prompt("Provide a new name for the preset:", fromName);
    if (toName === null || toName === fromName)
        return;
    else
        publishMessage(device, { command: "renamePreset", fromName, toName });
}

const deletePreset = (device, name) => {
    if (window.confirm("Are you sure you want to delete preset " + name + "?"))
        publishMessage(device, { command: "deletePreset", name });
}

let pubnub;

const setupPubNub = () => {
    console.log(config.pubnub);
    pubnub = new PubNub(config.pubnub);

    // add listener
    const listener = {
        status: (statusEvent) => {
            if (statusEvent.category === "PNConnectedCategory") {
                console.log("Connected");
            }
        },
        message: (messageEvent) => {
            console.log("message: ", messageEvent);
            if ("pixels" in messageEvent.message) {
                setLocalPixels(messageEvent.publisher, messageEvent.message["pixels"]);
            } else if ("presets" in messageEvent.message) {
                setLocalPresets(messageEvent.publisher, messageEvent.message["presets"]);
            }
        },
        presence: (presenceEvent) => {
            console.log(presenceEvent);
        }
    };
    pubnub.addListener(listener);

    // subscribe to device channel(s)
    let channels = config.devices.map(device => device.id + "_status");
    console.log(channels);
    pubnub.subscribe({ channels });
};

// run after page is loaded
window.onload = (event) => {
    setupPubNub();
    config.devices.forEach((device) => {
        setLocalPresets(device.id, []);
        getRemoteState(device.id);
    })
    updateDiwaliSeason();
    setInterval(updateDiwaliSeason, 60 * 1000);
};

window.addEventListener("pagehide", () => {
    [...activePreviews.keys()].forEach(stopPreview);
});

// publish message
const publishMessage = async (device, message) => {
    let channel = device + "_control";
    message.from = config.pubnub.userId;
    console.log(message);
    await pubnub.publish({ channel, message });
}

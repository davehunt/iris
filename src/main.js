const userId = "web";
const devices = [ "lokipizero2w", "yuzupizero2w" ];
window.localPixels = {}
window.localPresets = {};

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
    sim = document.getElementById(device);
    simPixels = sim.querySelectorAll('.pixel');
    for (i = 0; i < pixels.length; i++) {
        let color = pixels[i].slice(0, 3);
        simPixels[i].style["background-color"] = rgbToHex(...color);
        // TODO need a way to represent brightness
    }
}

const setLocalPresets = (device, presets) => {
    window.localPresets[device] = presets;
    container = document.querySelector("#" + device + " .presets");
    container.innerText = "";
    presets.forEach((preset) => {
        let name = preset["name"];
        let div = document.createElement('div');
        div.setAttribute("class", "simulator");
        div.setAttribute("name", name);
        let ol = document.createElement("ol");
        ol.appendChild(document.createTextNode(name + " "));
        preset["pixels"].forEach((pixel) => {
            let color = pixel.slice(0, 3)
            let li = document.createElement('li');
            li.setAttribute("class", "pixel");
            li.setAttribute("style", "background-color: " + rgbToHex(...color) + ";");
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
        loadIcon = document.createElement("i");
        loadIcon.setAttribute("class", "bi bi-box-arrow-left");
        loadButton.appendChild(loadIcon);
        buttonGroup.appendChild(loadButton);

        // send preset button
        sendButton = document.createElement('button');
        sendButton.setAttribute("class", "btn btn-sm btn-outline-secondary");
        sendButton.setAttribute("onclick", "loadPreset(getTargetDevice(this), '" + name + "'); setRemotePixels(getTargetDevice(this));");
        sendButton.setAttribute("data-bs-toggle", "tooltip");
        sendButton.setAttribute("data-bs-placement", "bottom");
        sendButton.setAttribute("title", "Send preset");
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
            deleteIcon = document.createElement("i");
            deleteIcon.setAttribute("class", "bi bi-trash");
            deleteButton.appendChild(deleteIcon);
            buttonGroup.appendChild(deleteButton);
        }

        ol.appendChild(buttonGroup);
        div.appendChild(ol);
        container.appendChild(div);
    })
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
    publishMessage(device, { command: "pressButton", button });
};

const clearRemotePixels = (device) => {
    publishMessage(device, { command: "clearPixels" });
};

const setRemotePixels = (device) => {
    message = { command: "setPixels", pixels: getLocalPixels(device) };
    publishMessage(device, message);
};

const loadLocalPixels = (device) => {
    let pixels = document.querySelectorAll('#' + device + ' .custom .pixel');
    for (i = 0; i < window.localPixels[device].length; i++) {
        let color = window.localPixels[device][i].slice(0, 3);
        let brightness = window.localPixels[device][i][3];
        pixels[i].querySelector("input[name=color]").value = rgbToHex(...color);
        pixels[i].querySelector("input[name=brightness]").value = brightness * 10;
    }
}

const loadPreset = (device, presetName) => {
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
    console.log(config);
    pubnub = new PubNub(config);

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
    let channels = devices.map(device => device + "_status");
    console.log(channels);
    pubnub.subscribe({ channels });
};

// run after page is loaded
window.onload = (event) => {
    setupPubNub();
    devices.forEach((device) => {
        getRemoteState(device);
    })
};

// publish message
const publishMessage = async (device, message) => {
    let channel = device + "_control";
    message.from = userId;
    console.log(message);
    await pubnub.publish({ channel, message });
}

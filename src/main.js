const userId = "web";

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

const setLocalPixels = (pixels) => {
    window.localPixels = pixels;
    simPixels = document.querySelectorAll('#current .pixel');
    for (i = 0; i < pixels.length; i++) {
        let color = pixels[i].slice(0, 3);
        simPixels[i].style["background-color"] = rgbToHex(...color);
        // TODO need a way to represent brightness
    }
}

const setLocalPresets = (presets) => {
    window.localPresets = presets;
    container = document.getElementById("presets");
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
        loadButton.setAttribute("class", "btn btn-outline-secondary");
        loadButton.setAttribute("onclick", "loadPreset('" + name + "');");
        loadIcon = document.createElement("i");
        loadIcon.setAttribute("class", "bi bi-box-arrow-left");
        loadButton.appendChild(loadIcon);
        buttonGroup.appendChild(loadButton);

        // send preset button
        sendButton = document.createElement('button');
        sendButton.setAttribute("class", "btn btn-outline-secondary");
        sendButton.setAttribute("onclick", "loadPreset('" + name + "'); setRemotePixels();");
        sendIcon = document.createElement("i");
        sendIcon.setAttribute("class", "bi bi-send");
        sendButton.appendChild(sendIcon);
        buttonGroup.appendChild(sendButton);

        if (!preset["default"]) {
            // rename preset button
            renameButton = document.createElement('button');
            renameButton.setAttribute("class", "btn btn-outline-secondary");
            renameButton.setAttribute("onclick", "renamePreset('" + name + "');");
            renameIcon = document.createElement("i");
            renameIcon.setAttribute("class", "bi bi-pencil");
            renameButton.appendChild(renameIcon);
            buttonGroup.appendChild(renameButton);

            // delete preset button
            deleteButton = document.createElement('button');
            deleteButton.setAttribute("class", "btn btn-outline-secondary");
            deleteButton.setAttribute("onclick", "deletePreset('" + name + "');");
            deleteIcon = document.createElement("i");
            deleteIcon.setAttribute("class", "bi bi-trash");
            deleteButton.appendChild(deleteIcon);
            buttonGroup.appendChild(deleteButton);
        }

        ol.appendChild(buttonGroup);
        div.appendChild(ol);
        container.appendChild(div);
    })
}

const fill = () => {
    pixels = document.querySelectorAll('#custom .pixel');
    color = pixels[0].querySelector("input[name=color]").value;
    brightness = pixels[0].querySelector("input[name=brightness]").value;
    for (i = 1; i < pixels.length; i++) {
        pixels[i].querySelector("input[name=color]").value = color;
        pixels[i].querySelector("input[name=brightness]").value = brightness;
    }
}

const getLocalPixels = () => {
    let pixels = []
    document.querySelectorAll('#custom .pixel').forEach((pixel) => {
        color = hexToRgb(pixel.querySelector("input[name=color]").value);
        brightness = pixel.querySelector("input[name=brightness]").value / 10;
        pixels.push([...color, brightness])
    });
    return pixels;
}

const getRemoteState = () => {
    getRemotePixels();
    getRemotePresets();
}

const getRemotePixels = () => {
    publishMessage({ command: "getPixels" });
}

const getRemotePresets = () => {
    publishMessage({ command: "getPresets" });
}

const pressButton = (button) => {
    publishMessage({ command: "pressButton", button });
};

const clearRemotePixels = () => {
    publishMessage({ command: "clearPixels" });
};

const setRemotePixels = () => {
    message = { command: "setPixels", pixels: getLocalPixels() };
    publishMessage(message);
};

const loadLocalPixels = () => {
    pixels = document.querySelectorAll('#custom .pixel');
    for (i = 0; i < window.localPixels.length; i++) {
        let color = window.localPixels[i].slice(0, 3);
        let brightness = window.localPixels[i][3];
        pixels[i].querySelector("input[name=color]").value = rgbToHex(...color);
        pixels[i].querySelector("input[name=brightness]").value = brightness * 10;
    }
}

const loadPreset = (presetName) => {
    let preset = window.localPresets.find(({ name }) => name === presetName);
    pixels = document.querySelectorAll('#custom .pixel');
    for (i = 0; i < preset["pixels"].length; i++) {
        let color = preset["pixels"][i].slice(0, 3);
        let brightness = preset["pixels"][i][3];
        pixels[i].querySelector("input[name=color]").value = rgbToHex(...color);
        pixels[i].querySelector("input[name=brightness]").value = brightness * 10;
    }
};

const savePreset = () => {
    let name = prompt("Provide a name for the preset:");
    if (name === null || name === "")
        return;
    else {
        let pixels = getLocalPixels();
        publishMessage({ command: "savePreset", name, pixels });
    }
}

const renamePreset = (fromName) => {
    let toName = prompt("Provide a new name for the preset:", fromName);
    if (toName === null || toName === fromName)
        return;
    else
        publishMessage({ command: "renamePreset", fromName, toName });
}

const deletePreset = (name) => {
    if (window.confirm("Are you sure you want to delete preset " + name + "?"))
        publishMessage({ command: "deletePreset", name });
}

let pubnub;

const setupPubNub = () => {
    pubnub = new PubNub({
        publishKey: "pub-c-d98680db-be18-4ee9-ba81-11117e35917d",
        subscribeKey: "sub-c-be8e17d5-8472-4e5d-a789-5bbd006d42f3",
        userId
    });

    // add listener
    const listener = {
        status: (statusEvent) => {
            if (statusEvent.category === "PNConnectedCategory") {
                console.log("Connected");
            }
        },
        message: (messageEvent) => {
            console.log("message: ", messageEvent.message);
            if ("pixels" in messageEvent.message) {
                setLocalPixels(messageEvent.message["pixels"]);
            } else if ("presets" in messageEvent.message) {
                setLocalPresets(messageEvent.message["presets"]);
            }
        },
        presence: (presenceEvent) => {
            console.log(presenceEvent);
        }
    };
    pubnub.addListener(listener);

    // subscribe to a channel
    pubnub.subscribe({
        channels: [userId]
    });
};

// run after page is loaded
window.onload = (event) => {
    setupPubNub();
    getRemoteState();
};

// publish message
const publishMessage = async (message) => {
    message.from = userId;
    const publishPayload = {
        channel: document.getElementById("target").value,
        message: message
    };
    await pubnub.publish(publishPayload);
}

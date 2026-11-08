// Browser-only frames matching the eight-LED effects in iris.py.
const clamp = (value, low = 0, high = 1) => Math.max(low, Math.min(high, value));
const mix = (a, b, amount) => a.map((value, i) => value + (b[i] - value) * amount);
const roundChannel = (value) => {
    // Python's round() resolves exact half-channel ties to the even integer.
    const lower = Math.floor(value);
    return value - lower === 0.5 ? lower + lower % 2 : Math.round(value);
};

class DiwaliPreview {
    constructor(random = Math.random) {
        this.duration = 60;
        this.lampColours = [
            [255, 110, 20], [255, 147, 41], [255, 183, 76], [255, 147, 41],
            [255, 147, 41], [255, 183, 76], [255, 147, 41], [255, 110, 20],
        ];
        this.rangoliColours = [[255, 0, 144], [0, 206, 190], [148, 0, 211], [255, 183, 76]];
        const sparkleColours = [[255, 0, 144], [0, 206, 190], [148, 0, 211], [0, 230, 90]];
        this.flicker = this.lampColours.map(() => [
            random() * 2 * Math.PI, random() * 2 * Math.PI,
            1.3 + random() * 0.8, 2.9 + random() * 1.4,
        ]);
        this.bursts = Array.from({ length: 3 }, (_, k) => [
            30.5 + k * 1.8, sparkleColours[Math.floor(random() * sparkleColours.length)],
        ]);
    }

    envelope(t, start, end) {
        return t >= start && t <= end ? clamp(Math.min(t - start, end - t)) : 0;
    }

    lamp(i, t) {
        const [p1, p2, w1, w2] = this.flicker[i];
        const wave = 0.3 * Math.sin(w1 * t + p1) + 0.2 * Math.sin(w2 * t + p2);
        const level = 0.5 + wave * clamp((this.duration - t) / 3);
        const [r, g, b] = this.lampColours[i];
        return [r, g * (0.85 + 0.15 * level), b, 0.08 + 0.12 * level];
    }

    rangoli(i, t) {
        const phase = Math.abs(i - 3.5) - 1.5 * (t - 16);
        const index = Math.floor(phase);
        const colours = this.rangoliColours;
        const modulo = (n) => ((n % colours.length) + colours.length) % colours.length;
        const colour = mix(colours[modulo(index)], colours[modulo(index + 1)],
            clamp((phase - index - 0.7) / 0.3));
        return [...colour, 0.15 + 0.03 * Math.sin(4 * t + i)];
    }

    sparkle(i, t) {
        let pixel = [255, 183, 76, 0.08];
        const distance = Math.abs(i - 3.5) - 0.5;
        this.bursts.forEach(([start, colour]) => {
            const age = t - start;
            if (age < 0 || age >= 1.2)
                return;
            const intensity = clamp(1 - Math.abs(distance - age * 5))
                * (1 - age / 1.2) * clamp(age / 0.15);
            pixel = mix(pixel, [...colour, 0.28], intensity);
        });
        return pixel;
    }

    frame(t) {
        return this.lampColours.map((_, i) => {
            const lit = clamp((t - i * 0.5) / 0.4);
            if (lit === 0)
                return [0, 0, 0, 0];
            let pixel = this.lamp(i, t);
            pixel[3] *= lit;
            pixel = mix(pixel, this.rangoli(i, t), this.envelope(t, 16, 24));
            pixel = mix(pixel, this.sparkle(i, t), this.envelope(t, 30, 36));
            return [...pixel.slice(0, 3).map(roundChannel),
                Math.round(clamp(pixel[3], 0, 0.3) * 1000) / 1000];
        });
    }
}

const marqueeFrame = (pattern, t) => {
    // Both device marquees currently advance every 0.1s, including Christmas.
    const steps = Math.floor(t * 10) + 1;
    return Array.from({ length: 8 }, (_, i) => {
        const index = steps - 8 + i;
        return index < 0 ? [0, 0, 0, 0] : pattern[index % pattern.length];
    });
};

const rainbowFrame = (seconds) => Array.from({ length: 8 }, (_, i) => {
    const hue = ((Math.floor(seconds * 100) % 360) + i * 22.5) % 360 / 60;
    const x = 1 - Math.abs(hue % 2 - 1);
    const sectors = [[1, x, 0], [x, 1, 0], [0, 1, x], [0, x, 1], [x, 0, 1], [1, 0, x]];
    return [...sectors[Math.floor(hue)].map(c => Math.floor(c * 255)), 0.1];
});

const firefoxFrame = (t) => {
    const fade = clamp(Math.min(t, 30 - t) / 1.5);
    const head = t * 8 / 6;
    return Array.from({ length: 8 }, (_, i) => {
        const globe = (1 + Math.sin(2 * Math.PI * i / 8 - t * 0.4)) / 2;
        let pixel = mix([18, 35, 160, 0.06], [85, 24, 185, 0.08], globe);
        // Circular lobes wrap the tail smoothly from LED 7 back to LED 0.
        for (const [offset, width, strength, colour] of [
            [2.5, 1.6, 0.65, [240, 48, 12, 0.18]],
            [1.25, 0.95, 0.85, [255, 106, 16, 0.24]],
            [0, 0.65, 1, [255, 192, 52, 0.28]],
        ]) {
            const angle = 2 * Math.PI * (i - head + offset) / 8;
            const lobe = Math.exp((Math.cos(angle) - 1) / (width * 2 * Math.PI / 8) ** 2);
            pixel = mix(pixel, colour, lobe * strength);
        }
        return [...pixel.slice(0, 3).map(roundChannel),
            Math.round(clamp(pixel[3] * fade, 0, 0.3) * 1000) / 1000];
    });
};

const SPECIAL_PRESETS = [
    { id: "rainbow", emoji: "🌈", name: "Rainbow", duration: 30,
        create: (epoch = 0) => (t) => rainbowFrame(epoch + t) },
    { id: "valentines", emoji: "💝", name: "Valentine's", duration: 10,
        create: () => (t) => marqueeFrame(
            [0.1, 0.1, 0.5, 0.5, 0.9, 0.9, 0.5, 0.5].map(b => [247, 0, 162, b]), t) },
    { id: "xmas", emoji: "🎄", name: "Christmas", duration: 10,
        create: () => (t) => marqueeFrame([[255, 0, 0, 0.1], [255, 255, 255, 0.1]], t) },
    { id: "diwali", emoji: "🪔", name: "Diwali", duration: 60, staysLit: true,
        create: () => {
            const celebration = new DiwaliPreview();
            return (t) => celebration.frame(t);
        } },
    { id: "firefox", emoji: "🦊", name: "Firefox", duration: 30,
        create: () => firefoxFrame },
];

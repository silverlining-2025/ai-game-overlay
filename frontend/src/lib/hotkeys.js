/**
 * Global hotkey registration via Tauri plugin.
 * Alt+O: toggle overlay, Alt+T: toggle click-through,
 * Alt+C: request advice, F9: toggle interactive mode.
 */
import { getCurrentWindow } from "@tauri-apps/api/window";
import { register, unregister } from "@tauri-apps/plugin-global-shortcut";
import { coachSocket } from "./websocket";
let clickThrough = true;
export async function setupHotkeys() {
    // Toggle overlay visibility
    await register("Alt+O", async (event) => {
        if (event.state === "Pressed") {
            const win = getCurrentWindow();
            const visible = await win.isVisible();
            if (visible) {
                await win.hide();
            }
            else {
                await win.show();
            }
        }
    });
    // Toggle click-through
    await register("Alt+T", async (event) => {
        if (event.state === "Pressed") {
            clickThrough = !clickThrough;
            const win = getCurrentWindow();
            await win.setIgnoreCursorEvents(clickThrough);
        }
    });
    // Request coach advice
    await register("Alt+C", (event) => {
        if (event.state === "Pressed") {
            coachSocket.send("request_suggestion", { context: "current_state" });
        }
    });
    // Toggle interactive mode (F9)
    await register("F9", async (event) => {
        if (event.state === "Pressed") {
            clickThrough = !clickThrough;
            const win = getCurrentWindow();
            await win.setIgnoreCursorEvents(clickThrough);
        }
    });
}
export async function cleanupHotkeys() {
    await unregister("Alt+O");
    await unregister("Alt+T");
    await unregister("Alt+C");
    await unregister("F9");
}

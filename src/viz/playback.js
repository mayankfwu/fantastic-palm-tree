export default function ({ data, parentElement, setTriggerValue }) {
    let scene = parentElement.querySelector("iframe");
    const isNew = !scene;
    if (isNew) {
        scene = document.createElement("iframe");
        scene.title = "Continuous 3D orbit";
        scene.setAttribute("sandbox", "allow-scripts");
        scene.style.cssText = "border:0;width:100%;height:500px;display:block";
        const json = JSON.stringify(data.packet).replaceAll("<", "\\u003c");
        scene.srcdoc = data.template.replace("__ENCOUNTER_DATA__", () => json);
        parentElement.appendChild(scene);
    }
    const requestBlock = event => {
        if (event.source === scene.contentWindow && event.data?.type === "orbit-next") {
            setTriggerValue("advance", event.data.sequence);
        }
    };
    window.addEventListener("message", requestBlock);
    if (!isNew) scene.contentWindow.postMessage({type: "orbit-block", packet: data.packet}, "*");
    return () => window.removeEventListener("message", requestBlock);
}

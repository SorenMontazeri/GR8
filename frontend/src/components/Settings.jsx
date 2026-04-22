import { useEffect, useState } from "react";

const DEFAULT_SETTINGS = {
  min_event_duration: 0,
  prompt_fullframe_snapshot: "",
  prompt_uniform_movement: "",
  fullframe_time: -1,
  uniform_samplerate: 1,
  uniform_samplerate_value: 0,
  movement_tracker_type: 1,
  movement_tracker_type_threshhold: 0,
  movement_samplerate: 1,
  movement_samplerate_value: 0,
};

const numericFields = new Set([
  "min_event_duration",
  "fullframe_time",
  "uniform_samplerate",
  "uniform_samplerate_value",
  "movement_tracker_type",
  "movement_tracker_type_threshhold",
  "movement_samplerate",
  "movement_samplerate_value",
]);

const inputClass =
  "w-full rounded border border-[#FFCC00] bg-[#333] px-2 py-1 text-white";

const labelClass = "flex flex-col gap-1 text-left";
const labelTextClass = "text-sm text-gray-300";

function SettingsSection({ title, children }) {
  return (
    <section className="flex flex-col gap-3 border-b border-gray-600 pb-5">
      <h3 className="text-lg font-bold text-[#FFCC00]">{title}</h3>
      {children}
    </section>
  );
}

export default function SettingsPanel() {
  const [settings, setSettings] = useState(DEFAULT_SETTINGS);
  const [saveStatus, setSaveStatus] = useState("idle");
  const [errorMessage, setErrorMessage] = useState("");

  useEffect(() => {
    async function loadSettings() {
      try {
        const response = await fetch("http://localhost:8000/api/settings");

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        const savedSettings = await response.json();
        setSettings((previousSettings) => ({
          ...previousSettings,
          ...savedSettings,
        }));
      } catch (error) {
        console.error("Failed to load settings:", error);
      }
    }

    loadSettings();
  }, []);

  function handleChange(event) {
    const { name, value } = event.target;

    setSettings((previousSettings) => ({
      ...previousSettings,
      [name]: numericFields.has(name) ? Number(value) : value,
    }));
  }

  async function handleSave(event) {
    event.preventDefault();
    setSaveStatus("saving");
    setErrorMessage("");

    try {
      const response = await fetch("http://localhost:8000/api/settings", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(settings),
      });
        console.log("Saving settings:", settings)


      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      setSaveStatus("saved");
    } catch (error) {
      setSaveStatus("error");
      setErrorMessage(error.message);
    }
  }

  return (
    <aside className="w-96 min-h-screen overflow-y-auto bg-[#222] border-r-4 border-[#FFCC00] p-4">
      <h2 className="text-xl font-bold text-[#FFCC00] mb-6">
        Inställningar
      </h2>

      <form className="flex flex-col gap-6" onSubmit={handleSave}>
        <SettingsSection title="General">
          <label className={labelClass}>
            <span className={labelTextClass}>Minimigrans for videolängd</span>
            <input
              type="number"
              min="0"
              className={inputClass}
              name="min_event_duration"
              value={settings.min_event_duration}
              onChange={handleChange}
            />
          </label>

          <label className={labelClass}>
            <span className={labelTextClass}>Prompt till LLM fullframe och snapshot</span>
            <textarea
              className={`${inputClass} min-h-20 resize-y`}
              name="prompt_fullframe_snapshot"
              placeholder="Skriv prompt..."
              value={settings.prompt_fullframe_snapshot}
              onChange={handleChange}
            />
          </label>

          <label className={labelClass}>
            <span className={labelTextClass}>Prompt till LLM uniform/movement</span>
            <textarea
              className={`${inputClass} min-h-20 resize-y`}
              name="prompt_uniform_movement"
              placeholder="Skriv prompt..."
              value={settings.prompt_uniform_movement}
              onChange={handleChange}
            />
          </label>
        </SettingsSection>

        <SettingsSection title="Fullframe">
          <label className={labelClass}>
            <span className={labelTextClass}>När ska fullframe tas?</span>
            <select
              className={inputClass}
              name="fullframe_time"
              value={settings.fullframe_time}
              onChange={handleChange}
            >
              <option value="-1">Samma tid som snapshot</option>
              <option value="0">0%</option>
              <option value="10">10%</option>
              <option value="20">20%</option>
              <option value="30">30%</option>
              <option value="40">40%</option>
              <option value="50">50%</option>
              <option value="60">60%</option>
              <option value="70">70%</option>
              <option value="80">80%</option>
              <option value="90">90%</option>
              <option value="100">100%</option>
            </select>
          </label>
        </SettingsSection>

        <SettingsSection title="Frames uniform">
          <label className={labelClass}>
            <span className={labelTextClass}>Uniform frame metod</span>
            <select
              className={inputClass}
              name="uniform_samplerate"
              value={settings.uniform_samplerate}
              onChange={handleChange}
            >
              <option value="1">Auto</option>
              <option value="2">Percent</option>
              <option value="3">Antal frames</option>
            </select>
          </label>

          <label className={labelClass}>
            <span className={labelTextClass}>Uniform frame method value</span>
            <input
              type="number"
              min="0"
              className={inputClass}
              name="uniform_samplerate_value"
              placeholder="Percent eller antal frames"
              value={settings.uniform_samplerate_value}
              onChange={handleChange}
            />
          </label>
        </SettingsSection>

        <SettingsSection title="Frames movement">
          <label className={labelClass}>
            <span className={labelTextClass}>Movement method</span>
            <select
              className={inputClass}
              name="movement_tracker_type"
              value={settings.movement_tracker_type}
              onChange={handleChange}
            >
              <option value="1">MQTT boxes</option>
              <option value="2">Frame change</option>
            </select>
          </label>

          <label className={labelClass}>
            <span className={labelTextClass}>Hur stor andring for nasta frame</span>
            <input
              type="number"
              min="0"
              className={inputClass}
              name="movement_tracker_type_threshhold"
              value={settings.movement_tracker_type_threshhold}
              onChange={handleChange}
            />
          </label>

          <label className={labelClass}>
            <span className={labelTextClass}>Movement frame metod</span>
            <select
              className={inputClass}
              name="movement_samplerate"
              value={settings.movement_samplerate}
              onChange={handleChange}
            >
              <option value="1">Auto</option>
              <option value="2">Percent</option>
              <option value="3">Antal frames</option>
            </select>
          </label>

          <label className={labelClass}>
            <span className={labelTextClass}>Movement frame metod varde</span>
            <input
              type="number"
              min="0"
              className={inputClass}
              name="movement_samplerate_value"
              placeholder="Percent eller antal frames"
              value={settings.movement_samplerate_value}
              onChange={handleChange}
            />
          </label>
        </SettingsSection>

        <button
          type="submit"
          className="bg-[#FFCC00] hover:bg-[#E6AD00] text-black py-2 px-4 rounded transition-colors disabled:opacity-60"
          disabled={saveStatus === "saving"}
        >
          {saveStatus === "saving" ? "Sparar..." : "Save"}
        </button>

        {saveStatus === "saved" ? (
          <p className="text-sm text-green-300">Inställningarna sparades.</p>
        ) : null}

        {saveStatus === "error" ? (
          <p className="text-sm text-red-300">
            Kunde inte spara inställningar: {errorMessage}
          </p>
        ) : null}
      </form>
    </aside>
  );
}

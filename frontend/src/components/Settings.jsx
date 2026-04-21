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
  return (
    <aside className="w-96 min-h-screen overflow-y-auto bg-[#222] border-r-4 border-[#FFCC00] p-4">
      <h2 className="text-xl font-bold text-[#FFCC00] mb-6">
        Inställningar
      </h2>

      <div className="flex flex-col gap-6">
        <SettingsSection title="General">
          <label className={labelClass}>
            <span className={labelTextClass}>Minimigrans for videolängd</span>
            <input
              type="number"
              min="0"
              className={inputClass}
              name="min_event_duration"
              defaultValue={0}
            />
          </label>

          <label className={labelClass}>
            <span className={labelTextClass}>Prompt till LLM fullframe och snapshot</span>
            <textarea
              className={`${inputClass} min-h-20 resize-y`}
              name="prompt_fullframe_snapshot"
              placeholder="Skriv prompt..."
            />
          </label>

          <label className={labelClass}>
            <span className={labelTextClass}>Prompt till LLM uniform/movement</span>
            <textarea
              className={`${inputClass} min-h-20 resize-y`}
              name="prompt_uniform_movement"
              placeholder="Skriv prompt..."
            />
          </label>
        </SettingsSection>

        <SettingsSection title="Fullframe">
          <label className={labelClass}>
            <span className={labelTextClass}>Nar ska fullframe tas?</span>
            <select className={inputClass} name="fullframe_time" defaultValue="-1">
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
            <select className={inputClass} name="uniform_samplerate" defaultValue="1">
              <option value="1">Auto</option>
              <option value="2">Percent</option>
              <option value="3">Antal frames</option>
            </select>
          </label>

          <label className={labelClass}>
            <span className={labelTextClass}>Uniform frame metod varde</span>
            <input
              type="number"
              min="0"
              className={inputClass}
              name="uniform_samplerate_value"
              placeholder="Percent eller antal frames"
            />
          </label>
        </SettingsSection>

        <SettingsSection title="Frames movement">
          <label className={labelClass}>
            <span className={labelTextClass}>Movement metod</span>
            <select className={inputClass} name="movement_tracker_type" defaultValue="1">
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
              defaultValue={0}
            />
          </label>

          <label className={labelClass}>
            <span className={labelTextClass}>Movement frame metod</span>
            <select className={inputClass} name="movement_samplerate" defaultValue="1">
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
            />
          </label>
        </SettingsSection>
      </div>
    </aside>
  );
}

import { useEffect, useState } from "react";

export default function Image({ name }) {
  const [images, setImages] = useState([]);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!name) {
      setImages([]);
      setError(null);
      setLoading(false);
      return;
    }

    async function load() {
      try {
        setLoading(true);
        setError(null);
        const res = await fetch(`http://localhost:8000/api/image/${name}`);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();

        // Normalize response to an array of { name, image }
        let normalized = [];

        if (Array.isArray(data)) {
          normalized = data.map((item, i) => {
            if (typeof item === "string") return { name: `${name} ${i + 1}`, image: item };
            if (item.image) return { name: item.name || `${name} ${i + 1}`, image: item.image };
            return { name: item.name || `${name} ${i + 1}`, image: item };
          });
        } else if (Array.isArray(data.images)) {
          normalized = data.images.map((item, i) => ({ name: item.name || `${name} ${i + 1}`, image: item.image || item }));
        } else if (data.image) {
          normalized = [{ name: data.name || name, image: data.image }];
        } else if (typeof data === "string") {
          normalized = [{ name, image: data }];
        } else {
          normalized = [{ name, image: data }];
        }

        setImages(normalized.filter((it) => it && it.image));
      } catch (e) {
        setImages([]);
        setError(e.message);
      } finally {
        setLoading(false);
      }
    }

    load();
  }, [name]);

  if (!name) return <p>Skriv ett namn och klicka på knappen.</p>;

  if (error) return <p>Failed to load image: {error}</p>;
  if (loading) return <p>Loading image...</p>;
  if (!images || images.length === 0) return <p>Inga resultat för den taggen.</p>;

  return (
    <div className="w-full">
      <h2 className="text-xl font-semibold mb-2">Results for “{name}”</h2>
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
        {images.map((it, idx) => (
          <div key={idx} className="bg-white rounded-lg p-2 shadow-sm">
            <h3 className="text-sm font-medium mb-1">{it.name}</h3>
            <img
              src={`data:image/jpeg;base64,${it.image}`}
              alt={it.name}
              style={{ width: "100%", borderRadius: "8px" }}
            />
          </div>
        ))}
      </div>
    </div>
  );
}

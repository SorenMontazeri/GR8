import { useEffect, useState } from "react";

export default function Image({ name }) {
  const [imgSrc, setImgSrc] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!name) {
      setImgSrc(null);
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

        setImgSrc(`data:image/jpeg;base64,${data.image}`);
      } catch (e) {
        setImgSrc(null);
        setError(e.message);
      } finally {
        setLoading(false);
      }
    }

    load();
  }, [name]);

  if (!name) return <p>Skriv ett namn och klicka på knappen.</p>;

  if (error) return <p>Failed to load image: {error}</p>;
  if (loading || !imgSrc) return <p>Loading image...</p>;

  return (
    <div>
      <h2>{name}</h2>
      <img
        src={imgSrc}
        alt={name}
        style={{ maxWidth: "500px", width: "100%", borderRadius: "12px" }}
      />
    </div>
  );
}

import { useEffect, useState } from "react";

const API_BASE_URL = "http://127.0.0.1:8000";

export default function Image({ searchString }) {
  const [imgSrc, setImgSrc] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
// Whenever the search string changes, we want to fetch a new image
  useEffect(() => {
    if (!searchString) {
      setImgSrc(null);
      setError(null);
      setLoading(false);
      return;
    }

    async function load() {
      //load image from backend, handle loading and error states
      try {
        setLoading(true);
        setError(null);
        const res = await fetch(`${API_BASE_URL}/api/image/${encodeURIComponent(searchString)}`);
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
  }, [searchString]);

  if (!searchString) return <p>Skriv ett namn och klicka på knappen.</p>;

  if (error) return <p>Failed to load image: {error}</p>;
  if (loading || !imgSrc) return <p>Loading image...</p>;

  return (
    // Display the image with a title
    <div>
      <h2>{searchString}</h2>
      <img
        src={imgSrc}
        alt={searchString}
        style={{ maxWidth: "500px", width: "100%", borderRadius: "12px" }}
      />
    </div>
  );
}

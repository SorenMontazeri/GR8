import { useState, useEffect } from "react";

export default function ImageCarousel({ searchString }) {
  const [images, setImages] = useState([]); 
  const [currentIndex, setCurrentIndex] = useState(0);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    // Om ingen söksträng finns, töm bilderna och gör inget mer
    if (!searchString) {
      setImages([]);
      return;
    }

    async function fetchSeq() {
      setLoading(true);
      try {
        const res = await fetch(`http://localhost:8000/api/sequence/${searchString}`);
        if (!res.ok) throw new Error("Kunde inte hämta bilder");
        
        const data = await res.json();
        
        // Vi antar att data.images är en array med base64-strängar
        setImages(data.images || []);
        setCurrentIndex(0); // Återställ till första bilden vid ny sökning
      } catch (e) { 
        console.error("Fetch error:", e); 
        setImages([]);
      } finally {
        setLoading(false);
      }
    }

    fetchSeq();
  }, [searchString]);

  // Visningslogik för tomma tillstånd
  if (!searchString) return <div className="text-white italic">Skriv in något för att söka...</div>;
  if (loading) return <div className="text-[#FFCC00] animate-pulse">Laddar sekvens...</div>;
  if (images.length === 0) return <div className="text-white">Ingen sekvens hittades för "{searchString}"</div>;

  // Navigeringsfunktioner
  const goNext = () => setCurrentIndex((prev) => (prev + 1) % images.length);
  const goPrev = () => setCurrentIndex((prev) => (prev - 1 + images.length) % images.length);

  return (
    <div className="flex flex-col items-center gap-4">
      <div className="flex items-center gap-4">
        <button 
          onClick={goPrev} 
          className="bg-[#FFCC00] p-3 rounded-full text-black font-bold hover:scale-110 transition-transform"
        >
          {"<"}
        </button>
        
        <div className="relative">
          <img 
            src={`data:image/jpeg;base64,${images[currentIndex]}`} 
            alt={`Sekvens bild ${currentIndex + 1}`}
            className="w-[400px] h-[300px] object-cover border-4 border-[#FFCC00] rounded-lg shadow-lg" 
          />
          <div className="absolute bottom-2 right-2 bg-black/50 text-white px-2 py-1 rounded text-xs">
            {currentIndex + 1} / {images.length}
          </div>
        </div>
        
        <button 
          onClick={goNext} 
          className="bg-[#FFCC00] p-3 rounded-full text-black font-bold hover:scale-110 transition-transform"
        >
          {">"}
        </button>
      </div>
      
      <p className="text-[#FFCC00] font-medium uppercase tracking-widest text-sm">
        Visar resultat för: {searchString}
      </p>
    </div>
  );
}
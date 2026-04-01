import { useState, useEffect } from "react";

export default function ImageCarousel({ searchString }) {
  
  const testImages = ["/bird.jpg", "/flower.jpg"];
  const [images, setImages] = useState(testImages); 
  const [currentIndex, setCurrentIndex] = useState(0);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    // Om ingen söksträng finns, visa testbilderna
    if (!searchString) {
      setImages(testImages);
      setCurrentIndex(0);
      return;
    }

    // Hämta bilderna från DB
    async function fetchSeq() {
      setLoading(true);
      try {
        const res = await fetch(`http://localhost:8000/api/sequence/${searchString}`);
        if (!res.ok) throw new Error("Kunde inte hämta data");
        
        const data = await res.json();
        
        if (data.images && data.images.length > 0) {
          setImages(data.images); 
        } else {
          setImages([]); 
        }
        setCurrentIndex(0); 
      } catch (e) { 
        console.error("Fetch error:", e); 
        setImages([]); 
      } finally {
        setLoading(false);
      }
    }

    fetchSeq();
  }, [searchString]);

  // Bläddringsfunktioner
  const goNext = () => setCurrentIndex((prev) => (prev + 1) % images.length);
  const goPrev = () => setCurrentIndex((prev) => (prev - 1 + images.length) % images.length);

  // --- Din fina visningslogik ---
  if (loading) {
    return <div className="text-[#FFCC00] animate-pulse">Laddar sekvens...</div>;
  }

  if (images.length === 0) {
    return <div className="text-white">Ingen sekvens hittades för "{searchString}"</div>;
  }

  // Hjälpfunktion för att hantera både lokala filer och Base64 från DB
  const renderImage = () => {
    const currentImg = images[currentIndex];
    if (typeof currentImg === "string" && currentImg.startsWith("/")) {
      return currentImg;
    }
    return `data:image/jpeg;base64,${currentImg}`;
  };

  return (
    <div className="flex flex-col items-center gap-4">
      <div className="flex items-center gap-4">
        <button 
          onClick={goPrev} 
          className="bg-[#FFCC00] p-2 rounded-full text-black font-bold hover:bg-[#e6b800]"
        >
          {"<"}
        </button>
        
        <div className="relative">
          <img 
            src={renderImage()} 
            alt={`Bild ${currentIndex + 1}`}
            className="w-[300px] h-[200px] object-cover border-2 border-[#FFCC00] rounded" 
          />
        </div>
        
        <button 
          onClick={goNext} 
          className="bg-[#FFCC00] p-2 rounded-full text-black font-bold hover:bg-[#e6b800]"
        >
          {">"}
        </button>
      </div>

      <div className="flex flex-col items-center">
        <span className="text-[#FFCC00] font-bold">
          {currentIndex + 1} / {images.length}
        </span>
        <span className="text-gray-400 text-xs mt-1">
          {searchString ? `Visar: ${searchString}` : "Visar testbilder"}
        </span>
      </div>
    </div>
  );
}
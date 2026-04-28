import React, { useState, useEffect } from "react"; 

function Analys({ goHome }) {
  const [stats, setStats] = useState({
    snapshot: 0,
    fullframe: 0,
    uniform: 0,
    varied: 0,
  });

  // Get likes from database
  useEffect(() => {
    const fetchData = async () => {
      try {
        const response = await fetch('http://127.0.0.1:8000/api/stats');

        const data = await response.json();

        // Uppdatera statet med data från databasen
        setStats({
          snapshot: data.snapshot,
          fullframe: data.fullframe,
          uniform: data.uniform, 
          varied: data.varied
        });
      } catch (error) {
        console.error("Error fetching data:", error);
      }
    };

    fetchData();
  }, []);

  // Function to clear analysis
  const handleClear = async () => {
  try {
    const response = await fetch('http://127.0.0.1:8000/api/admin/reset', {
      method: 'POST', 
      headers: {
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      throw new Error('Kunde inte nollställa databasen');
    }

    // Uppdatera statet visuellt direkt
    setStats({
      snapshot: 0,
      fullframe: 0,
      urval1: 0,
      urval2: 0
    });

    console.log("Analysen är nollställd!");

  } catch (error) {
    console.error("Ett fel uppstod:", error);
    alert("Kunde inte nollställa resultaten i databasen");
  }
};


  return (
    <div className="flex flex-col items-center justify-start min-h-screen pt-20">

      <button
        onClick={goHome}
        className="absolute top-8 right-8 bg-[#FFCC00] hover:bg-[#E6AD00] text-black rounded"
      >
        Home
      </button>
      
      <h1 className="text-3xl font-bold text-[#FFCC00] mb-12 self-center">
        ANALYS
      </h1>

      <div className="border-4 border-[#FFCC00] p-10 w-full">
        <h2 className="text-3xl font-bold mb-6">Antal likes</h2>
        
        <div className="space-y-4 text-2xl font-medium">
          <div className="flex justify-between max-w-xs">
            <span>Snapshot:</span> 
            <span className="text-[#FFCC00]">{stats.snapshot}</span>
          </div>
          
          <div className="flex justify-between max-w-xs">
            <span>Fullframe:</span> 
            <span className="text-[#FFCC00]">{stats.fullframe}</span>
          </div>
          
          <div className="pt-8 space-y-4 border-t border-gray-500/30">
            <div className="flex justify-between max-w-sm italic text-gray-200">
              <p>Uniform:</p> 
              <p className="text-[#FFCC00] not-italic font-bold">{stats.uniform}</p>
            </div>
            
            <div className="flex justify-between max-w-sm italic text-gray-200">
              <p>Variered:</p> 
              <p className="text-[#FFCC00] not-italic font-bold">{stats.varied}</p>
            </div>
          </div>
        </div>
      </div>
      <button
      onClick={handleClear}
      className="mt-8 bg-[#FFCC00] hover:bg-[#E6AD00] text-black rounded px-4 py-2"
    >
      Clear analysis
    </button>
    </div>
  );
}

export default Analys;
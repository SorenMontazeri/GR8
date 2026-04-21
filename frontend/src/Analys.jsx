import React, { useState, useEffect } from "react"; 

function Analys({ goHome }) {
  const [stats, setStats] = useState({
    snapshot: 25, // 0
    fullframe: 12, // 0
    urval1: 7, // 0
    urval2: 18 // 0
  });

  // Function to clear analysis
  const handleClear = async () => {
    try {
      const response = await fetch('-------API_URL------/reset', {
        method: 'PATCH', // Eller 'PUT' beroende på API
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          snapshot: 0,
          fullframe: 0,
          urval1: 0,
          urval2: 0
        }),
      });

      if (!response.ok) {
        throw new Error('Could not reset results in database');
      }
      setStats({
        snapshot: 0,
        fullframe: 0,
        urval1: 0,
        urval2: 0
      });

      console.log("Analysis is cleared!");

    } catch (error) {
      console.error("Error occured:", error);
      alert("Could not reset results in database");
    }
  };

  // kommentera ut när databas är inkopplad
 
//   useEffect(() => {
//     const fetchData = async () => {
//       try {
//         // Link to database
//         const response = await fetch('DIN_API_URL_HÄR');
        
//         if (!response.ok) {
//           throw new Error('Could not get data');
//         }

//         const data = await response.json();

//         // 3. Update state with the data from the database
//         // We assume that the database sends an object with the same names
//         setStats({
//           snapshot: data.snapshot,
//           fullframe: data.fullframe,
//           urval1: data.urval1,
//           urval2: data.urval2
//         });
//       } catch (error) {
//         console.error("Error fetching data:", error);
//       }
//     };

//     fetchData();
//   }, []); // Runs once when the page loads

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
              <p>Urvalsstrategi 1:</p> 
              <p className="text-[#FFCC00] not-italic font-bold">{stats.urval1}</p>
            </div>
            
            <div className="flex justify-between max-w-sm italic text-gray-200">
              <p>Urvalsstrategi 2:</p> 
              <p className="text-[#FFCC00] not-italic font-bold">{stats.urval2}</p>
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
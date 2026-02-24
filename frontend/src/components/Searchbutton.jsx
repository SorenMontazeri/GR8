import { useState } from 'react';

function SearchButton({ id }) {
  const [clicked, setClicked] = useState(false);
  const [userInfo, setUserInfo] = useState(null);
  const handleSave = () => {
    // Send id to backend 
    fetch(`http://localhost:8000/api/info/${id}`)
    .then(res => {
      if (!res.ok) throw new Error("Hittade inte ID");
      return res.json(); // creates a json format
    })
    .then(data => {
      console.log("Data mottagen:", data);
      setUserInfo(data); // Save the data in state
      setClicked(true);
    })
    .catch(err => {
      console.error("Fel:", err);
      setUserInfo(null);
    });
  };

  return (
    <div>
    <button 
      className="px-4 py-2 bg-blue-500 text-white rounded shadow"
      onClick={handleSave}
      style={{ backgroundColor: clicked ? 'green' : '#3b82f6' }}
    >
      {clicked ? 'Sparat i databasen!' : 'Spara data'}
    </button>

    <div>
      {userInfo ? (
          <div>
            <p>ID: {userInfo.id}</p>
            <p>Namn: {userInfo.name}</p>
          </div>
        ) : (
          <p>Ingen data hämtad ännu. Skriv ett ID i rutan och klicka på knappen.</p>
        )}
      </div>
    </div>
  );
}

export default SearchButton;
import { useState } from 'react';

function SearchButton({ name }) {
  const [clicked, setClicked] = useState(false);

  const handleSave = () => {
    // Här skickar vi 'name' till din backend
    fetch("http://localhost:8000/api/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username: name }) 
    })
    .then(res => {
      if (res.ok) setClicked(true);
    })
    .catch(err => console.error("Fel:", err));
  };

  return (
    <button 
      className="px-4 py-2 bg-blue-500 text-white rounded shadow"
      onClick={handleSave}
      style={{ backgroundColor: clicked ? 'green' : '#3b82f6' }}
    >
      {clicked ? 'Sparat i databasen!' : 'Spara data'}
    </button>
  );
}

export default SearchButton;
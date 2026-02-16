import { useEffect, useState } from 'react';

function Search() {
  const [clicked, setClicked] = useState(false);

  useEffect(() => {
    fetch("http://localhost:8000/api/info/2")
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then(({ number }) => {
        console.log("number:", number);
      })
      .catch((err) => {
        console.error("fetch failed:", err);
      });
  }, []);

  return (
    <button className="bg-blue-500"
      onClick={() => setClicked(true)}
      style={{ color: clicked ? 'green' : 'red' }}
    >
      {clicked ? 'Sparat i databasen!' : 'Spara data'}
    </button>
  );
}

export default Search

import { useState } from 'react';

function App() {
  const [clicked, setClicked] = useState(false);

  return (
    <button className="bg-blue-500"
      onClick={() => setClicked(true)}
      style={{ color: clicked ? 'green' : 'red' }}
    >
      {clicked ? 'Sparat i databasen!' : 'Spara data'}
    </button>
  );
}
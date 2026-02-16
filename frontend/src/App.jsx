import { useState } from 'react'
import './App.css'
import SearchButton from './components/SearchButton'
import TextSearch from './components/TextSearch.jsx'

function App() {
  // Vi håller namnet här så att båda komponenterna kan prata med det
  const [name, setName] = useState("");

  return (
    <div className="App flex flex-col items-center justify-center min-h-screen">
      <h1 className="text-3xl font-bold text-gray-800">GR8</h1>
      
      {/* Skicka ner name och setName som props */}
      <TextSearch name={name} setName={setName} />
      
      {/* Skicka ner name så knappen vet vad den ska spara */}
      <SearchButton id={name} />
      
      <p className="mt-4 text-gray-500">Du skriver just nu: {name}</p>
    </div>
   )
}

export default App
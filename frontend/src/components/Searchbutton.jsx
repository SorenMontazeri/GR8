
/* Search button that runs the function handleSearch when the user is clicking 
on it which updates the submittedName state in App.jsx */
export default function SearchButton({ id, onClick }) {
  return (
    <button
      onClick={onClick}
      className="px-4 py-2 rounded bg-[#FFCC00] text-black border-none hover:bg-[#FFB300] focus:outline-none focus:ring-2 focus:ring-[#FFCC00] focus:ring-offset-2"
    >
      Search
    </button>
  );
}
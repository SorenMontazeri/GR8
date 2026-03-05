
/* Search button that runs the function handleSearch when the user is clicking 
on it which updates the submittedName state in App.jsx */
export default function SearchButton({ id, onClick }) {
  return (
    <button
      onClick={onClick}
      className="px-4 py-2 rounded bg-black text-white"
    >
      Search
    </button>
  );
}
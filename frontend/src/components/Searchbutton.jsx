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
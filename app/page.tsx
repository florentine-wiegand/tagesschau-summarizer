import { getSortedSummariesData } from '@/lib/api';
import Link from 'next/link';

export default function Home() {
  const allSummariesData = getSortedSummariesData();

  if (allSummariesData.length === 0) {
    return (
      <div className="text-center py-20 bg-gray-900/40 rounded-3xl border border-gray-800">
        <h2 className="text-2xl font-semibold text-gray-300">Noch keine Zusammenfassungen verfügbar.</h2>
        <p className="text-gray-500 mt-2">Das System wartet auf die nächste Tagesschau.</p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
      {allSummariesData.map(({ id, date, title }) => (
        <Link href={`/summary/${id}`} key={id} className="group flex flex-col justify-between p-6 bg-gray-900 border border-gray-800 rounded-2xl hover:border-gray-600 transition-colors">
          <div>
            <div className="text-sm text-blue-400 font-medium mb-2">{date}</div>
            <h2 className="text-xl font-semibold text-white mb-3 group-hover:text-blue-300 transition-colors line-clamp-2">{title}</h2>
          </div>
          <div className="mt-4 inline-flex items-center text-sm text-gray-400 group-hover:text-white transition-colors">
            Zusammenfassung lesen <span className="ml-2">→</span>
          </div>
        </Link>
      ))}
    </div>
  );
}

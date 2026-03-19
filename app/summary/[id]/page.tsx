import { getSummaryData, getSortedSummariesData } from '@/lib/api';
import Link from 'next/link';
import { Metadata } from 'next';

export async function generateStaticParams() {
  const summaries = getSortedSummariesData();
  return summaries.map((summary) => ({
    id: summary.id,
  }));
}

export async function generateMetadata({ params }: { params: { id: string } }): Promise<Metadata> {
  const summaryData = await getSummaryData(params.id);
  return {
    title: `${summaryData.title} | Tagesschau AI`,
  }
}

export default async function SummaryPage({ params }: { params: { id: string } }) {
  const summaryData = await getSummaryData(params.id);

  return (
    <article className="bg-gray-900/50 border border-gray-800 rounded-2xl p-6 md:p-10 mb-8">
      <Link href="/" className="inline-flex items-center text-sm text-gray-400 hover:text-white mb-8 transition-colors">
        ← Zurück zur Übersicht
      </Link>
      
      <header className="mb-10">
        <div className="text-sm text-blue-400 font-medium mb-3">{summaryData.date}</div>
        <h1 className="text-3xl md:text-4xl font-bold text-white mb-6 leading-tight">{summaryData.title}</h1>
        
        {summaryData.videoId && (
            <a 
              href={`https://youtube.com/watch?v=${summaryData.videoId}`} 
              target="_blank" 
              rel="noreferrer"
              className="inline-flex items-center px-4 py-2 bg-red-600/10 text-red-500 rounded-full text-sm font-medium hover:bg-red-600/20 transition-colors"
            >
              ▶ Auf YouTube ansehen
            </a>
        )}
      </header>
      
      <div 
        className="prose prose-invert max-w-none" 
        dangerouslySetInnerHTML={{ __html: summaryData.contentHtml }} 
      />
    </article>
  );
}

import fs from 'fs';
import path from 'path';
import matter from 'gray-matter';
import { remark } from 'remark';
import html from 'remark-html';

const summariesDirectory = path.join(process.cwd(), 'content/summaries');

export type SummaryMeta = {
  id: string;
  title: string;
  date: string;
  videoId: string;
};

export type Summary = SummaryMeta & {
  contentHtml: string;
};

export function getSortedSummariesData(): SummaryMeta[] {
  if (!fs.existsSync(summariesDirectory)) {
    return [];
  }
  const fileNames = fs.readdirSync(summariesDirectory);
  const allSummariesData = fileNames.filter(f => f.endsWith('.md')).map((fileName) => {
    const id = fileName.replace(/\.md$/, '');
    const fullPath = path.join(summariesDirectory, fileName);
    const fileContents = fs.readFileSync(fullPath, 'utf8');

    const matterResult = matter(fileContents);

    return {
      id,
      ...matterResult.data,
    } as SummaryMeta;
  });

  return allSummariesData.sort((a, b) => {
    if (a.date < b.date) {
      return 1;
    } else {
      return -1;
    }
  });
}

export async function getSummaryData(id: string): Promise<Summary> {
  const fullPath = path.join(summariesDirectory, `${id}.md`);
  const fileContents = fs.readFileSync(fullPath, 'utf8');

  const matterResult = matter(fileContents);

  const processedContent = await remark()
    .use(html)
    .process(matterResult.content);
  const contentHtml = processedContent.toString();

  return {
    id,
    contentHtml,
    ...matterResult.data,
  } as Summary;
}

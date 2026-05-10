'use server';

import { redirect } from 'next/navigation';

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:4000';

export async function submitLabel(formData: FormData): Promise<void> {
  const project = String(formData.get('project') ?? 'demo');
  const metric = String(formData.get('metric') ?? '');
  const recordId = String(formData.get('record_id') ?? '');
  const userEmail = String(formData.get('user_email') ?? '').trim();
  const score = Number(formData.get('score'));
  const rationale = String(formData.get('rationale') ?? '').trim() || null;
  const tagsRaw = String(formData.get('tags') ?? '').trim();
  const tags = tagsRaw
    ? tagsRaw
        .split(',')
        .map((t) => t.trim())
        .filter(Boolean)
    : [];
  const queueId = String(formData.get('queue_id') ?? '');

  if (!metric || !recordId || !userEmail || Number.isNaN(score)) {
    redirect(`/labels?project=${project}&metric=${metric}&error=missing_fields`);
  }

  const resp = await fetch(`${API_URL}/v1/labels`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      project,
      metric_slug: metric,
      record_id: recordId,
      user_email: userEmail,
      score,
      rationale,
      tags,
    }),
    cache: 'no-store',
  });

  if (!resp.ok) {
    const err = await resp.text().catch(() => 'unknown');
    redirect(
      `/labels?project=${project}&metric=${metric}&error=${encodeURIComponent(err.slice(0, 80))}`,
    );
  }

  redirect(
    `/labels?project=${project}&metric=${metric}&user=${encodeURIComponent(userEmail)}&queue=${queueId}&done=1`,
  );
}

export async function refreshQueue(formData: FormData): Promise<void> {
  const project = String(formData.get('project') ?? 'demo');
  const metric = String(formData.get('metric') ?? '');
  const queueSize = Number(formData.get('queue_size') ?? 50);
  if (!metric) return;
  await fetch(`${API_URL}/v1/queue/refresh`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ project, metric, queue_size: queueSize }),
    cache: 'no-store',
  });
  redirect(`/labels?project=${project}&metric=${metric}`);
}

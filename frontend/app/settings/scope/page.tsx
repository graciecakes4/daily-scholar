// /settings/scope now resolves to the library view; old links/bookmarks to
// this bare path still land somewhere sensible instead of 404ing.
import { redirect } from 'next/navigation';

export default function ScopeSettingsIndex() {
  redirect('/settings/scope/library');
}

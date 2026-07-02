// /settings/account now resolves to the profile view; old links/bookmarks
// to this bare path still land somewhere sensible instead of 404ing.
import { redirect } from 'next/navigation';

export default function AccountSettingsIndex() {
  redirect('/settings/account/profile');
}

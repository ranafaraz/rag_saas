import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

const PUBLIC_PATHS = ['/login', '/signup', '/verify', '/select-workspace'];

export function proxy(req: NextRequest) {
  const { pathname } = req.nextUrl;

  const isPublic = PUBLIC_PATHS.some((p) => pathname.startsWith(p));
  const isWorkspace = pathname.startsWith('/w/');

  const wsSlug = req.cookies.get('ws_slug')?.value;

  if (isWorkspace && !wsSlug) {
    return NextResponse.redirect(new URL('/login', req.url));
  }

  if (isPublic && wsSlug) {
    return NextResponse.redirect(new URL(`/w/${wsSlug}/chat`, req.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ['/((?!api|_next/static|_next/image|favicon.ico|.*\\.png$).*)'],
};

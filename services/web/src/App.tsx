import { useEffect, useState } from 'react'
import { Gallery } from './gallery/Gallery'
import { DemoScreen } from './screens/Demo'
import { MerchantScreens } from './screens/Merchant'
import { OfficerScreens } from './screens/Officer'

export default function App() {
  const [path, setPath] = useState(location.pathname.replace(/\/$/, '') || '/')
  useEffect(() => {
    const update = () => setPath(location.pathname.replace(/\/$/, '') || '/')
    addEventListener('popstate', update)
    return () => removeEventListener('popstate', update)
  }, [])
  function navigate(next: string) {
    history.pushState({}, '', next + location.search); setPath(next); window.scrollTo(0, 0)
  }
  if (path === '/__gallery') return <Gallery />
  if (path === '/demo') return <DemoScreen />
  return path.startsWith('/officer') ? <OfficerScreens path={path} navigate={navigate} /> : <MerchantScreens path={path} navigate={navigate} />
}

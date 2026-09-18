import { useState } from 'react'
import {
  Banknote,
  CircleHelp,
  CreditCard,
  FileText,
  Home,
  Inbox,
  Languages,
  MessageCircle,
  QrCode,
  ReceiptIndianRupee,
  Share2,
  Volume2,
  WalletCards
} from 'lucide-react'
import {
  AmountText,
  AppBar,
  BottomNav,
  BottomSheet,
  Card,
  Chip,
  ChipGroup,
  EmptyState,
  HeaderBand,
  LanguagePicker,
  MicButton,
  PhoneFrame,
  Skeleton,
  Snackbar,
  Stepper,
  StickyCTA,
  ThresholdProgress,
  TierBar,
  TileGrid,
  TxnRow
} from '../components'

function Wordmark() {
  return <span className="text-lg font-bold tracking-tight"><span className="text-white">Paytm</span> <span className="text-cyan">Hisaab</span></span>
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="border-b border-hairline px-0 py-7 last:border-b-0">
      <h2 className="mb-4 px-1 text-xs font-bold uppercase tracking-[0.14em] text-muted">{title}</h2>
      {children}
    </section>
  )
}

export function Gallery() {
  const [chip, setChip] = useState('sale')
  const [language, setLanguage] = useState('kn')
  const [nav, setNav] = useState('home')
  const [snackbar, setSnackbar] = useState(true)

  return (
    <main className="mx-auto min-h-dvh w-full max-w-[360px] overflow-x-hidden bg-bg px-3 pb-12">
      <div className="safe-top pt-6">
        <p className="text-sm font-bold text-navy"><span>Paytm</span> <span className="text-cyan">Hisaab</span></p>
        <h1 className="mt-1 text-xl font-bold text-ink">Foundation gallery</h1>
        <p className="mt-1 text-sm text-muted">360 px component verification route</p>
      </div>

      <Section title="AppBar">
        <AppBar title="Payment details" backLabel="Go back" onBack={() => undefined} language="ಕನ್ನಡ" languageLabel="Choose language" onLanguageClick={() => undefined} helpLabel="Get help" onHelp={() => undefined} />
      </Section>

      <Section title="HeaderBand">
        <HeaderBand businessName="Ananya Stores" collectionLabel="Today's collection" amount="₹18,340" paymentSummary="64 payments" wordmark={<Wordmark />} />
      </Section>

      <Section title="BottomNav">
        <BottomNav position="contained" ariaLabel="Primary navigation" activeId={nav} onChange={setNav} items={[
          { id: 'home', label: 'Home', icon: <Home /> },
          { id: 'payments', label: 'Payments', icon: <CreditCard /> },
          { id: 'hisaab', label: 'Hisaab', icon: <ReceiptIndianRupee /> },
          { id: 'assistant', label: 'Assistant', icon: <MessageCircle /> }
        ]} />
      </Section>

      <Section title="PhoneFrame">
        <PhoneFrame label="Phone frame preview" className="h-[420px]">
          <HeaderBand businessName="Ananya Stores" collectionLabel="Today" amount="₹4,200" wordmark={<Wordmark />} />
          <div className="p-4"><Card><p className="text-sm font-semibold text-navy">Phone-first content area</p><p className="mt-1 text-xs text-muted">The full frame is 412 × 892 on a desktop.</p></Card></div>
        </PhoneFrame>
      </Section>

      <Section title="TileGrid">
        <Card>
          <TileGrid ariaLabel="Business tools" onSelect={() => undefined} items={[
            { id: 'payments', label: 'Payments', icon: <CreditCard /> },
            { id: 'settlements', label: 'Settlements', icon: <Banknote /> },
            { id: 'soundbox', label: 'Soundbox', icon: <Volume2 /> },
            { id: 'hisaab', label: 'Hisaab', icon: <ReceiptIndianRupee />, badge: '3' },
            { id: 'share', label: 'Share with CA', icon: <Share2 /> },
            { id: 'language', label: 'Language', icon: <Languages /> },
            { id: 'notices', label: 'Notices', icon: <FileText /> },
            { id: 'help', label: 'Help', icon: <CircleHelp /> }
          ]} />
        </Card>
      </Section>

      <Section title="Card">
        <div className="space-y-3">
          <Card><p className="text-base font-semibold text-navy">Default card</p><p className="mt-1 text-sm text-muted">A flat surface with the one approved elevation.</p></Card>
          <Card padding="compact" className="border border-hairline"><p className="text-sm text-ink">Compact bordered variant</p></Card>
        </div>
      </Section>

      <Section title="TxnRow">
        <Card padding="none" className="overflow-hidden">
          <TxnRow name="Ravi Kumar" time="21 Mar, 7:47 PM" amount="₹4,200" channelIcon={<QrCode />} channelLabel="UPI QR" label="Sale" tier={1} tierLabel="Tier 1 evidence" onClick={() => undefined} />
          <TxnRow name="Meera S" time="21 Mar, 6:12 PM" amount="₹15,000" channelIcon={<WalletCards />} channelLabel="UPI" label="Needs you" tier={3} tierLabel="Tier 3 evidence" />
        </Card>
      </Section>

      <Section title="AmountText">
        <Card className="flex flex-wrap items-end justify-between gap-3">
          <AmountText amount="₹4,200" credit prefix="+" />
          <AmountText amount="₹42.2 L" size="large" />
          <AmountText amount="₹1.2 Cr" size="large" />
        </Card>
      </Section>

      <Section title="EmptyState">
        <Card><EmptyState icon={<Inbox />} title="Nothing needs your attention" description="New items will appear here when action is needed." actionLabel="Refresh" onAction={() => undefined} /></Card>
      </Section>

      <Section title="Chip">
        <div className="flex gap-2"><Chip selected>Selected</Chip><Chip>Unselected</Chip><Chip disabled>Disabled</Chip></div>
      </Section>

      <Section title="ChipGroup">
        <ChipGroup label="Choose what this payment was" value={chip} onChange={setChip} options={[
          { value: 'sale', label: 'Sale' }, { value: 'family', label: 'Family' }, { value: 'own', label: 'My own money' }, { value: 'unsure', label: 'Not sure' }
        ]} />
      </Section>

      <Section title="StickyCTA">
        <StickyCTA position="contained" label="Continue" secondaryLabel="Not now" onSecondary={() => undefined} onClick={() => undefined} />
      </Section>

      <Section title="MicButton">
        <MicButton label="Hold to talk" holdingLabel="Listening… release to send" onHoldStart={() => undefined} onHoldEnd={() => undefined} className="w-full" />
      </Section>

      <Section title="LanguagePicker">
        <LanguagePicker label="Choose a language" value={language} onChange={setLanguage} languages={[
          { code: 'kn', nativeName: 'ಕನ್ನಡ', secondaryName: 'Kannada' },
          { code: 'hi', nativeName: 'हिन्दी', secondaryName: 'Hindi' },
          { code: 'ta', nativeName: 'தமிழ்', secondaryName: 'Tamil' },
          { code: 'te', nativeName: 'తెలుగు', secondaryName: 'Telugu' }
        ]} />
      </Section>

      <Section title="Snackbar">
        <Snackbar visible={snackbar} message="Your answer was recorded." tone="success" actionLabel="Dismiss" onAction={() => setSnackbar(false)} />
        {!snackbar && <button type="button" onClick={() => setSnackbar(true)} className="min-h-touch rounded-chip px-4 text-sm font-semibold text-navy">Show snackbar</button>}
      </Section>

      <Section title="BottomSheet">
        <BottomSheet title="Payment details" description="Recorded information for this credit" closeLabel="Close payment details" trigger={<button type="button" className="min-h-touch w-full rounded-chip bg-cyan px-5 text-sm font-bold text-navy">Open bottom sheet</button>}>
          <Card className="border border-hairline shadow-none"><div className="flex justify-between gap-3"><span className="text-sm text-muted">Amount</span><AmountText amount="₹4,200" /></div><div className="mt-3 flex justify-between gap-3"><span className="text-sm text-muted">Reference</span><span className="amount-numerals text-sm font-semibold">UPI-8120914</span></div></Card>
        </BottomSheet>
      </Section>

      <Section title="Stepper">
        <Card>
          <Stepper ariaLabel="Case progress" steps={[
            { id: 'opened', title: 'Payments on hold', meta: '09:30', status: 'complete' },
            { id: 'found', title: 'Disputed payment found', description: 'Matched independently by reference and amount.', meta: '09:34', status: 'complete' },
            { id: 'review', title: 'Officer reviewing', description: 'Your evidence pack is ready.', status: 'current' },
            { id: 'sent', title: 'Sent to bank and police', status: 'upcoming' }
          ]} />
        </Card>
      </Section>

      <Section title="ThresholdProgress">
        <Card>
          <ThresholdProgress current={3_460_000} threshold={4_000_000} currentLabel="₹34.6 L so far" thresholdLabel="₹40 L" projectedLabel="Projected crossing" projectedDate="14 Mar" />
        </Card>
      </Section>

      <Section title="TierBar">
        <Card>
          <TierBar ariaLabel="Evidence strength by tier" segments={[
            { tier: 1, label: 'Direct records', value: 54 }, { tier: 2, label: 'Strong context', value: 28 }, { tier: 3, label: 'Supporting', value: 12 }, { tier: 4, label: 'Weak', value: 6 }
          ]} />
        </Card>
      </Section>

      <Section title="Skeleton loader">
        <Card className="flex items-center gap-3">
          <Skeleton className="h-12 w-12 shrink-0 rounded-full" />
          <div className="flex-1 space-y-2"><Skeleton className="h-4 w-2/3" /><Skeleton className="h-3 w-full" /></div>
        </Card>
      </Section>
    </main>
  )
}

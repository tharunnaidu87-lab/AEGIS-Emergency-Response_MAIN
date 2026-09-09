import { Link } from 'react-router-dom';

export default function IntakeMethodSelector({ active }: { active: 'APP' | 'SMS' | 'CALL' }) {
  return <section className="intake-methods" aria-labelledby="intake-method-heading">
    <h2 id="intake-method-heading">How do you want to report?</h2>
    <nav aria-label="Reporting method">
      {([
        ['APP', '/report', 'REPORT ONLINE', 'Fill in the emergency form.'],
        ['SMS', '/sms', 'TEXT / SMS', 'Type what is happening.'],
        ['CALL', '/call', 'VOICE / CALL', 'Speak, review and send.'],
      ] as const).map(([id, path, label, description]) =>
        <Link key={id} to={path} aria-current={active === id ? 'page' : undefined}>
          <strong>{label}</strong><span>{description}</span>
        </Link>)}
    </nav>
  </section>;
}

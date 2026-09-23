import { Link } from 'react-router-dom';

export default function IntakeMethodSelector({ active }: { active: 'APP' | 'SMS' | 'CALL' }) {
  return <section className="intake-methods" aria-labelledby="intake-method-heading">
    <h2 id="intake-method-heading">Choose a reporting method</h2>
    <nav aria-label="Reporting method">
      {([
        ['APP', '/report', 'ONLINE FORM', 'Complete the emergency report.'],
        ['SMS', '/sms', 'TEXT / SMS', 'Describe the emergency in writing.'],
        ['CALL', '/call', 'VOICE / CALL', 'Speak, review, and submit.'],
      ] as const).map(([id, path, label, description]) =>
        <Link key={id} to={path} aria-current={active === id ? 'page' : undefined}>
          <strong>{label}</strong><span>{description}</span>
        </Link>)}
    </nav>
  </section>;
}

interface HelpSection {
  lang: "es" | "en" | "he";
  dir: "ltr" | "rtl";
  label: string;
  title: string;
  body: { heading: string; text: string }[];
}

// Spanish first — the Spanish-native learner is the one most likely to
// need this (can't read Hebrew script at all; the Hebrew-native learner
// can at least puzzle through English). See SPEC.md §8 for why the rest
// of the UI stays English-only — this is a deliberate, scoped exception.
const SECTIONS: HelpSection[] = [
  {
    lang: "es",
    dir: "ltr",
    label: "Español",
    title: "Cómo funciona Lingua",
    body: [
      {
        heading: "Umbral de fluidez",
        text: 'Cada palabra necesita que la marques "la sabía" un cierto número de veces (ajustable en Ajustes) antes de contar como "fluida". Una vez fluida, la palabra deja el estudio normal — solo vuelve a aparecer de vez en cuando en una "ronda mixta", para comprobar que no la has olvidado.',
      },
      {
        heading: "Rondas de repaso",
        text: 'Cada 15 repasos aparece una "ronda de recuperación" con las palabras que fallaste recientemente. Cada 30 repasos aparece una "ronda mixta" más amplia, que también puede incluir palabras ya fluidas.',
      },
      {
        heading: "Qué significa cada estadística",
        text: '"Vistas" son todas las palabras que has estudiado alguna vez. "Pendientes hoy" son las que tocan repasar ahora mismo. "Racha" son los días seguidos con actividad; "Mejor" es tu récord histórico. "Meta diaria" es tu objetivo de repasos por día, que puedes cambiar en Ajustes.',
      },
      {
        heading: "Marcar con estrella",
        text: "Puedes marcar cualquier palabra con una estrella, desde la tarjeta de estudio o desde la tabla de palabras. Las palabras marcadas aparecen con más frecuencia en el repaso.",
      },
      {
        heading: "Restablecer el progreso",
        text: 'La opción "Zona de peligro" en Ajustes borra TODO tu progreso (no tu PIN ni tus ajustes) de forma permanente. Necesita una contraseña y que escribas "RESET" para confirmar — no hay forma de deshacerlo.',
      },
    ],
  },
  {
    lang: "en",
    dir: "ltr",
    label: "English",
    title: "How Lingua works",
    body: [
      {
        heading: "Fluency threshold",
        text: 'Each word needs you to mark it "knew it" a certain number of times (adjustable in Settings) before it counts as "fluent". Once fluent, a word leaves regular study — it only comes back occasionally in a "mixed round," to check you haven\'t forgotten it.',
      },
      {
        heading: "Review rounds",
        text: 'Every 15 reviews, a "recovery round" appears with words you missed recently. Every 30 reviews, a broader "mixed round" appears, which can also include already-fluent words.',
      },
      {
        heading: "What each stat means",
        text: '"Seen" is every word you\'ve ever studied. "Due today" is what\'s waiting for review right now. "Streak" is consecutive days with activity; "Best" is your all-time record. "Daily goal" is your target review count per day, changeable in Settings.',
      },
      {
        heading: "Starring",
        text: "You can star any word, from the study card or the word table. Starred words resurface more often in review.",
      },
      {
        heading: "Resetting progress",
        text: 'The "Danger zone" in Settings permanently wipes ALL your progress (not your PIN or settings). It needs a password and typing "RESET" to confirm — there is no undo.',
      },
    ],
  },
  {
    lang: "he",
    dir: "rtl",
    label: "עברית",
    title: "איך לינגואה עובד",
    body: [
      {
        heading: "סף שטף",
        text: 'כל מילה צריכה שתסמן אותה "ידעתי" מספר מסוים של פעמים (ניתן לשינוי בהגדרות) לפני שהיא נחשבת "שוטפת". ברגע שמילה שוטפת, היא יוצאת מהלימוד הרגיל — היא תופיע שוב רק מדי פעם ב"סבב מעורב", כדי לוודא שלא שכחת אותה.',
      },
      {
        heading: "סבבי חזרה",
        text: 'כל 15 חזרות מופיע "סבב התאוששות" עם מילים שטעית בהן לאחרונה. כל 30 חזרות מופיע "סבב מעורב" רחב יותר, שיכול לכלול גם מילים שכבר שוטפות.',
      },
      {
        heading: "מה כל נתון אומר",
        text: '"נראו" הן כל המילים שאי פעם למדת. "לחזרה היום" הן המילים שממתינות לחזרה כרגע. "רצף" הם ימים רצופים עם פעילות; "השיא" הוא השיא ההיסטורי שלך. "יעד יומי" הוא מספר החזרות היעד ליום, הניתן לשינוי בהגדרות.',
      },
      {
        heading: "סימון בכוכב",
        text: "אפשר לסמן כל מילה בכוכב, מכרטיס הלימוד או מטבלת המילים. מילים מסומנות מופיעות בתדירות גבוהה יותר בחזרה.",
      },
      {
        heading: "איפוס התקדמות",
        text: '"אזור הסכנה" בהגדרות מוחק לצמיתות את כל ההתקדמות שלך (לא את הקוד הסודי או ההגדרות). נדרשים סיסמה והקלדת "RESET" לאישור — אין דרך לבטל את הפעולה.',
      },
    ],
  },
];

export function HelpPage({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-ink">
      <div className="flex items-center justify-between border-b border-parchment/10 px-4 py-4 sm:px-6">
        <h1 className="text-xl font-bold">Help</h1>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close help"
          className="flex h-8 w-8 items-center justify-center rounded-full bg-surfacemuted text-parchment/70 hover:text-parchment"
        >
          ✕
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-6 sm:px-6">
        <div className="mx-auto flex max-w-md flex-col gap-3">
          {SECTIONS.map((section, i) => (
            <details key={section.lang} open={i === 0} className="rounded-2xl bg-surface p-4">
              <summary className="cursor-pointer text-lg font-bold text-ember">{section.label}</summary>
              <div dir={section.dir} className="mt-3 flex flex-col gap-4">
                <p className="text-sm font-semibold text-bridge">{section.title}</p>
                {section.body.map((item) => (
                  <div key={item.heading}>
                    <p className="font-semibold text-parchment">{item.heading}</p>
                    <p className="mt-1 text-sm text-parchment/70">{item.text}</p>
                  </div>
                ))}
              </div>
            </details>
          ))}
        </div>
      </div>
    </div>
  );
}

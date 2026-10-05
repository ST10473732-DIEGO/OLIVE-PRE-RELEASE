# OLIVE End-User Licence Agreement

> **DRAFT — OWNER/LEGAL REVIEW REQUIRED.**
> This draft was prepared by release engineering for OLIVE 1.0. It is **not legal advice**, has not
> been reviewed by a lawyer, and is **not in force**. It must not be shipped with, displayed by or
> accepted in any OLIVE build until the owner has had it reviewed for each country where OLIVE will
> be offered (consumer-protection law, warranty law, governing law and jurisdiction in particular).
> Items needing a decision are marked **[OWNER]**.
>
> This agreement covers **official OLIVE binary builds** only. It is separate from, and does not
> change, the proprietary source licence in `LICENSE`, which governs the private source repository.

Version: draft 0.1 (2026-10-03) · Applies to: OLIVE 1.0 official builds for Linux, Windows and macOS

## 1. Who this agreement is between

This agreement is between you and **Diego De Oliveira** ("the Licensor"), the copyright holder of
OLIVE. **[OWNER]** Confirm the contracting party (an individual or a company), its address and a
contact for licence questions.

By installing or using an official OLIVE build, you accept this agreement. If you do not accept
it, do not install or use OLIVE.

## 2. What this agreement covers

"OLIVE" means the official OLIVE desktop application in object-code form, as distributed by the
Licensor or a distributor the Licensor authorises, including its updates, built-in assets, artwork
and documentation, but **excluding Third-Party Components** (section 6).

## 3. Licence grant

Subject to this agreement, the Licensor grants you a personal, non-exclusive, non-transferable,
revocable licence to:

1. install OLIVE on computers that you own or control;
2. use OLIVE for your own personal or internal business purposes; and
3. make a reasonable number of backup copies of the installer.

**[OWNER]** Decide whether commercial use, use within organisations, or a limit on the number of
devices applies, and whether OLIVE is offered free of charge.

## 4. Restrictions

Except to the extent applicable law expressly permits it despite this restriction, you may not:

1. copy OLIVE except as allowed in section 3;
2. distribute, publish, sell, rent, lease, lend, sublicense or otherwise make OLIVE available to
   anyone else, including by hosting it as a service for others, unless the Licensor permits it in
   writing;
3. modify, adapt, translate or create derivative works of OLIVE;
4. decompile, disassemble or reverse-engineer OLIVE, or try to derive its source code;
5. remove, change or hide any copyright, trademark, licence or attribution notice; or
6. use OLIVE to break the law or infringe anyone's rights.

Restrictions 3 and 4 do not apply to the extent that a Third-Party Component's licence gives you
that right, or to the extent mandatory law (for example interoperability rights under EU law)
gives it to you.

## 5. Your data and local AI

OLIVE runs its AI on your computer. Your chats, files, notes, drawings and memory are stored on
your computer, in the OLIVE data folder. The Licensor does not receive them.

Some optional features use the internet, for example live answers (NOW), downloading runtimes and
models during setup, and OLIVE Connect World through a relay that **you** choose and operate.
When you use them, the services you contact receive the data needed to answer you, under their
own terms. **[OWNER]** Link a privacy notice before public release.

You are responsible for how you use what OLIVE generates. AI output can be wrong, incomplete or
inappropriate; check it before relying on it.

## 6. Third-Party Components

OLIVE includes and works with software, libraries, fonts, models and model weights made by others
("Third-Party Components"), including Electron and Chromium, CPython, Python and npm libraries,
and, when you choose to install them during setup, the Ollama runtime, AI models and optional
components such as Playwright.

**Third-Party Components are licensed to you under their own licences, not under this agreement.**
Their notices are shipped with OLIVE (`resources/legal/` in the installed application) and shown
during setup where a licence applies. Nothing in this agreement limits rights those licences give
you. Where setup downloads a component from its publisher, you obtain it from that publisher under
the publisher's licence; some model licences include use restrictions that you must follow.

## 7. Updates

The Licensor may provide updates. Updates are covered by this agreement unless they come with
different terms. OLIVE does not update itself without your action. **[OWNER]** Confirm once an
update channel exists.

## 8. Ownership

OLIVE is licensed, not sold. The Licensor and its licensors keep all rights not expressly granted
to you. The names OLIVE and DMDO and the OLIVE logos may not be used except to describe OLIVE
accurately.

## 9. Termination

This agreement ends automatically if you breach it. You may end it at any time by uninstalling
OLIVE. When it ends, stop using OLIVE and delete your copies. Your own data stays yours; ending
the agreement never deletes it.

## 10. No warranty

To the extent permitted by law, OLIVE is provided "as is" and "as available", without warranty of
any kind, express or implied, including merchantability, fitness for a particular purpose,
accuracy and non-infringement. **[OWNER/LEGAL]** Consumer law in many countries gives rights that
cannot be excluded; this section must be adapted so it does not purport to exclude them.

## 11. Limitation of liability

To the extent permitted by law, the Licensor is not liable for indirect, incidental, special or
consequential damages, or for loss of data, profits or business, arising from OLIVE or this
agreement. **[OWNER/LEGAL]** Set an overall cap, and keep the carve-outs mandatory law requires
(for example for death or personal injury caused by negligence, fraud, or gross negligence).

## 12. Export and sanctions

You must comply with export-control and sanctions laws that apply to you and to OLIVE.

## 13. Governing law

**[OWNER/LEGAL]** Choose the governing law and courts, consistent with the consumer-protection
rules of the countries where OLIVE is offered.

## 14. Entire agreement

This agreement, together with the Third-Party Component licences, is the entire agreement about
the use of official OLIVE builds. If a provision is unenforceable, the rest remains in effect.

---

Owner checklist before this can be used:

- [ ] Legal review in each launch country; consumer-law adaptations to sections 10 and 11.
- [ ] Contracting party, contact address and governing law (sections 1 and 13).
- [ ] Commercial-use and device-count decisions (section 3).
- [ ] A privacy notice (section 5).
- [ ] Decide how acceptance is shown (installer page, first-run screen, or both).
- [ ] Confirm that the third-party notices shipped in `resources/legal/` are complete
      (see `THIRD_PARTY_NOTICES.md`).

# state/

Database SQLite di laboratorio (`SqliteReservationStore`, implementazione durevole
di RIFERIMENTO del contratto `ReservationStore` del Core).

- NON è storage di produzione.
- NON vive dentro P2 né dentro il Core canonical.
- Ogni test scrive il proprio file `*.db` qui; i dump leggibili sono in `../evidence/`.

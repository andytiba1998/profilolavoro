import pygame
import sys

# --- Costanti ---
LARGHEZZA = 540
ALTEZZA = 620
CELLE = 3
DIM_CELLA = LARGHEZZA // CELLE

BIANCO      = (255, 255, 255)
NERO        = (20,  20,  20)
GRIGIO      = (200, 200, 200)
GRIGIO_SCU  = (150, 150, 150)
BLU         = (52,  101, 164)
ROSSO       = (204, 0,   0)
VERDE       = (78,  154, 6)
SFONDO      = (245, 245, 245)
SFONDO_CEL  = (255, 255, 255)
HOVER_CEL   = (230, 240, 255)
LINEA       = (180, 180, 180)

pygame.init()
schermo = pygame.display.set_mode((LARGHEZZA, ALTEZZA))
pygame.display.set_caption("Gioco del Tris")

font_simbolo = pygame.font.SysFont("DejaVu Sans", 120, bold=True)
font_stato   = pygame.font.SysFont("DejaVu Sans", 26, bold=True)
font_btn     = pygame.font.SysFont("DejaVu Sans", 20, bold=True)
font_punteg  = pygame.font.SysFont("DejaVu Sans", 18)


def crea_tavola():
    return [[" "] * CELLE for _ in range(CELLE)]


def controlla_vincitore(tavola, giocatore):
    for i in range(CELLE):
        if all(tavola[i][j] == giocatore for j in range(CELLE)):
            return [(i, j) for j in range(CELLE)]
        if all(tavola[j][i] == giocatore for j in range(CELLE)):
            return [(j, i) for j in range(CELLE)]
    if all(tavola[i][i] == giocatore for i in range(CELLE)):
        return [(i, i) for i in range(CELLE)]
    if all(tavola[i][CELLE - 1 - i] == giocatore for i in range(CELLE)):
        return [(i, CELLE - 1 - i) for i in range(CELLE)]
    return []


def tavola_piena(tavola):
    return all(tavola[i][j] != " " for i in range(CELLE) for j in range(CELLE))


def disegna_pulsante(surf, testo, rettangolo, colore_sfondo, colore_testo, hover=False):
    colore = tuple(min(c + 20, 255) for c in colore_sfondo) if hover else colore_sfondo
    pygame.draw.rect(surf, colore, rettangolo, border_radius=8)
    pygame.draw.rect(surf, GRIGIO_SCU, rettangolo, 2, border_radius=8)
    etichetta = font_btn.render(testo, True, colore_testo)
    surf.blit(etichetta, etichetta.get_rect(center=rettangolo.center))


def disegna_tutto(schermo, stato):
    schermo.fill(SFONDO)
    tavola      = stato["tavola"]
    giocatore   = stato["giocatore"]
    vincitore   = stato["vincitore"]
    celle_vince = stato["celle_vincenti"]
    pareggio    = stato["pareggio"]
    punteggi    = stato["punteggi"]
    mouse_pos   = pygame.mouse.get_pos()

    # --- Intestazione punteggio ---
    pygame.draw.rect(schermo, BIANCO, (0, 0, LARGHEZZA, 70))
    pygame.draw.line(schermo, LINEA, (0, 70), (LARGHEZZA, 70), 2)

    testo_x = font_punteg.render(f"X  {punteggi['X']}", True, BLU)
    testo_o = font_punteg.render(f"O  {punteggi['O']}", True, ROSSO)
    testo_p = font_punteg.render(f"Pareggi  {punteggi['pareggi']}", True, GRIGIO_SCU)
    schermo.blit(testo_x, (40, 25))
    schermo.blit(testo_o, (LARGHEZZA - 110, 25))
    schermo.blit(testo_p, testo_p.get_rect(centerx=LARGHEZZA // 2, y=25))

    # --- Griglia ---
    offset_y = 70
    for riga in range(CELLE):
        for col in range(CELLE):
            x = col * DIM_CELLA
            y = offset_y + riga * DIM_CELLA
            rect_cella = pygame.Rect(x + 4, y + 4, DIM_CELLA - 8, DIM_CELLA - 8)

            # Colore sfondo cella
            if (riga, col) in celle_vince:
                colore_cella = VERDE
            elif tavola[riga][col] == " " and not vincitore and not pareggio:
                hover = rect_cella.collidepoint(mouse_pos)
                colore_cella = HOVER_CEL if hover else SFONDO_CEL
            else:
                colore_cella = SFONDO_CEL

            pygame.draw.rect(schermo, colore_cella, rect_cella, border_radius=10)
            pygame.draw.rect(schermo, LINEA, rect_cella, 2, border_radius=10)

            # Simbolo
            simbolo = tavola[riga][col]
            if simbolo != " ":
                colore_sim = BLU if simbolo == "X" else ROSSO
                if (riga, col) in celle_vince:
                    colore_sim = BIANCO
                testo = font_simbolo.render(simbolo, True, colore_sim)
                schermo.blit(testo, testo.get_rect(center=rect_cella.center))

    # --- Barra di stato ---
    stato_y = offset_y + CELLE * DIM_CELLA + 10
    pygame.draw.rect(schermo, BIANCO, (0, offset_y + CELLE * DIM_CELLA, LARGHEZZA, 80))
    pygame.draw.line(schermo, LINEA, (0, offset_y + CELLE * DIM_CELLA), (LARGHEZZA, offset_y + CELLE * DIM_CELLA), 2)

    if vincitore:
        msg = f"Giocatore {vincitore} ha vinto!"
        colore_msg = BLU if vincitore == "X" else ROSSO
    elif pareggio:
        msg = "Pareggio!"
        colore_msg = GRIGIO_SCU
    else:
        colore_turno = BLU if giocatore == "X" else ROSSO
        msg = f"Turno del giocatore {giocatore}"
        colore_msg = colore_turno

    testo_stato = font_stato.render(msg, True, colore_msg)
    schermo.blit(testo_stato, testo_stato.get_rect(centerx=LARGHEZZA // 2, y=stato_y + 10))

    # --- Pulsante Nuova Partita ---
    btn_rect = pygame.Rect(LARGHEZZA // 2 - 90, stato_y + 42, 180, 36)
    hover_btn = btn_rect.collidepoint(mouse_pos)
    disegna_pulsante(schermo, "Nuova partita", btn_rect, GRIGIO, NERO, hover_btn)

    pygame.display.flip()
    return btn_rect


def nuova_partita():
    return {
        "tavola":        crea_tavola(),
        "giocatore":     "X",
        "vincitore":     None,
        "celle_vincenti": [],
        "pareggio":      False,
    }


def main():
    orologio = pygame.time.Clock()
    punteggi = {"X": 0, "O": 0, "pareggi": 0}
    stato = nuova_partita()
    stato["punteggi"] = punteggi

    while True:
        btn_nuova = disegna_tutto(schermo, stato)

        for evento in pygame.event.get():
            if evento.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

            if evento.type == pygame.MOUSEBUTTONDOWN and evento.button == 1:
                mx, my = evento.pos

                # Click su "Nuova partita"
                if btn_nuova.collidepoint(mx, my):
                    stato = nuova_partita()
                    stato["punteggi"] = punteggi
                    continue

                # Click su una cella
                if stato["vincitore"] or stato["pareggio"]:
                    continue

                offset_y = 70
                col = mx // DIM_CELLA
                riga = (my - offset_y) // DIM_CELLA
                if 0 <= riga < CELLE and 0 <= col < CELLE:
                    if stato["tavola"][riga][col] == " ":
                        stato["tavola"][riga][col] = stato["giocatore"]

                        celle_vince = controlla_vincitore(stato["tavola"], stato["giocatore"])
                        if celle_vince:
                            stato["vincitore"] = stato["giocatore"]
                            stato["celle_vincenti"] = celle_vince
                            punteggi[stato["giocatore"]] += 1
                        elif tavola_piena(stato["tavola"]):
                            stato["pareggio"] = True
                            punteggi["pareggi"] += 1
                        else:
                            stato["giocatore"] = "O" if stato["giocatore"] == "X" else "X"

        orologio.tick(60)


if __name__ == "__main__":
    main()

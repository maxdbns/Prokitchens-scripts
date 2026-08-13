"""Helper pour signaler les runs verts mais vides dans GitHub Actions.

Un run peut être marqué succès sans rien insérer (API qui renvoie 0 résultat
sans erreur). warn_if_zero émet une annotation ::warning:: visible dans le
résumé du run — sans faire échouer le job (0 peut être légitime, ex. dimanche).
"""


def warn_if_zero(label: str, count: int) -> None:
    if count == 0:
        print(
            f"::warning::{label} : 0 résultat sur ce run — "
            "vérifier que la source n'est pas vide ou en panne"
        )

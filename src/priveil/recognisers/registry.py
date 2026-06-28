from presidio_analyzer import EntityRecognizer

from priveil.recognisers.au_abn import AUABNRecogniser
from priveil.recognisers.au_acn import AUACNRecogniser
from priveil.recognisers.au_bsb import AUBSBRecogniser
from priveil.recognisers.au_medicare import AUMedicareRecogniser
from priveil.recognisers.au_phone import AUPhoneRecogniser
from priveil.recognisers.au_tfn import AUTFNRecogniser


def build_recognisers() -> list[EntityRecognizer]:
    """Return all AU-specific recognisers for registration with the AnalyzerEngine.

    Order matters — more specific recognisers (checksum-validated) first so they
    take precedence over overlapping generic patterns.

    Returns:
        Ordered list of EntityRecognizer instances.
    """
    return [
        AUTFNRecogniser(),
        AUMedicareRecogniser(),
        AUABNRecogniser(),
        AUACNRecogniser(),
        AUBSBRecogniser(),
        AUPhoneRecogniser(),
    ]

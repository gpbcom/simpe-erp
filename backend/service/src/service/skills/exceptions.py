class MTInvalidSkillCatalogException(Exception):
    """Exception raised when a skill-catalogue operation fails."""


class MTSkillTypeNotFound(MTInvalidSkillCatalogException):
    """Exception raised when the named skill type does not exist."""


class MTSkillTypeAlreadyExists(MTInvalidSkillCatalogException):
    """Exception raised when the code is already used by another entry."""


class MTSkillTypeUnknownCode(MTInvalidSkillCatalogException):
    """Exception raised when a requirement names a code the catalogue lacks.

    Notes:
        Raised on the way in, when a service or a quote line is saved, rather
        than left to the planner. A requirement naming a code nobody can
        declare fails every planning run it touches, with a message that reads
        as a staffing problem — "nobody has declared XYZ" is true and useless
        when XYZ was a typo.
    """


class MTSkillTypeInUse(MTInvalidSkillCatalogException):
    """Exception raised when deleting an entry something still refers to.

    Notes:
        No foreign key protects the references, so this check is what stands in
        for one. Retiring the entry is offered instead: it stops the code being
        chosen again while leaving every declared skill that names it still
        resolvable.
    """

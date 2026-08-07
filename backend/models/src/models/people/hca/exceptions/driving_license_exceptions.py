class MTInvalidDrivingLicenseException(Exception):
    """Exception raised when an invalid DrivingLicense field is provided."""


class MTDrivingLicenseInvalidCategories(MTInvalidDrivingLicenseException):
    """Exception raised when an invalid ``categories`` list is provided."""


class MTDrivingLicenseInvalidNumber(MTInvalidDrivingLicenseException):
    """Exception raised when an invalid ``number`` value is provided."""


class MTDrivingLicenseInvalidObtainedOn(MTInvalidDrivingLicenseException):
    """Exception raised when an invalid ``obtained_on`` value is provided."""


class MTDrivingLicenseInvalidExpiresOn(MTInvalidDrivingLicenseException):
    """Exception raised when an invalid ``expires_on`` value is provided."""

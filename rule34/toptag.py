class TopTag:
    def __init__(self, rank: int, tagname: str, percentage: int):
        self._rank = rank
        self._tagname = tagname
        self._percentage = percentage
    
    def __from_dict(json: dict):
        return TopTag(json["rank"], json["tagname"], json["percentage"] * 100)
        
    @property
    def rank(self) -> int:
        return self._rank
    
    @property
    def tagname(self) -> str:
        return self._tagname
    
    @property
    def percentage(self) -> int:
        return self._percentage
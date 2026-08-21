from app.core.logging import logger


class RecursiveCharacterTextSplitter:
    """
    Splits text documents recursively using a list of separator characters.
    Ensures text blocks fit into target chunk sizes while maintaining overlap.
    """

    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        separators: list[str] | None = None,
    ) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators or ["\n\n", "\n", " ", ""]

        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("Chunk overlap must be smaller than chunk size.")

    def _split_text(self, text: str, separators: list[str]) -> list[str]:
        """Recursively splits text using the hierarchy of separators."""
        final_chunks = []

        # If text is already small enough, return it as a single chunk
        if len(text) <= self.chunk_size:
            return [text]

        # If we ran out of separators, split by hard slicing
        if not separators:
            return [
                text[i : i + self.chunk_size]
                for i in range(0, len(text), self.chunk_size - self.chunk_overlap)
            ]

        # Use the first separator
        separator = separators[0]
        next_separators = separators[1:]

        # Split text by current separator
        if separator == "":
            # Character-level split
            splits = list(text)
        else:
            splits = text.split(separator)

        # Process splits and recursively split any that exceed chunk_size
        current_doc = []
        for split in splits:
            # Re-add separator if it's not empty and not the last element
            item = split + separator if separator != "" else split

            if len(item) > self.chunk_size:
                # Flush current buffer first
                if current_doc:
                    final_chunks.extend(self._merge_splits(current_doc))
                    current_doc = []
                # Recursively split the long segment
                rec_splits = self._split_text(split, next_separators)
                final_chunks.extend(rec_splits)
            else:
                current_doc.append(item)

        if current_doc:
            final_chunks.extend(self._merge_splits(current_doc))

        return final_chunks

    def _merge_splits(self, splits: list[str]) -> list[str]:
        """Merges adjacent small splits into chunks of size up to self.chunk_size."""
        docs = []
        current_chunk: list[str] = []
        current_len = 0

        for split in splits:
            split_len = len(split)
            # If adding this split exceeds chunk_size, save current chunk and start a new one
            if current_len + split_len > self.chunk_size:
                if current_chunk:
                    docs.append("".join(current_chunk))

                # Implement overlap by keeping elements from current chunk
                # Rollback elements until length is under chunk_overlap
                overlap_chunk = []
                overlap_len = 0
                for item in reversed(current_chunk):
                    if overlap_len + len(item) <= self.chunk_overlap:
                        overlap_chunk.insert(0, item)
                        overlap_len += len(item)
                    else:
                        break

                current_chunk = overlap_chunk
                current_len = overlap_len

            current_chunk.append(split)
            current_len += split_len

        if current_chunk:
            docs.append("".join(current_chunk))

        return docs

    def split_text(self, text: str) -> list[str]:
        """
        Splits the input document text into small chunks.
        """
        if not text.strip():
            return []
        chunks = self._split_text(text, self.separators)
        logger.info(
            f"Split document text of length {len(text)} into {len(chunks)} chunks."
        )
        return chunks
